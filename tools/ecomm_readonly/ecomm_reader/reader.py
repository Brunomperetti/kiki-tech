"""Shared bounded query state machine. No binding, persistence or backend."""

import time
from .catalog import decode, pagination, candidates
from .policy import (
    HOST,
    BARCODE,
    MAX_REQUESTS,
    MAX_SECONDS,
    Request,
    page_url,
    public_addresses,
)
from .safety import Code, Failure


def query_contract():
    return {
        "mode": "OFFLINE_ONLY",
        "real_network_enabled": False,
        "method": "GET",
        "first_page": page_url(1),
        "second_page": "Only if validated page-1 pagination proves page 2 exists",
        "max_requests": MAX_REQUESTS,
        "max_seconds_per_request": MAX_SECONDS,
        "automatic_retries": 0,
        "follow_redirects": False,
        "postgresql": False,
        "kiki_backend": False,
        "external_writes": False,
        "credential_input_supported_by_cli": False,
    }


class InventoryReader:
    def __init__(self, resolver, wire, credential, *, clock=time.monotonic):
        if (
            getattr(resolver, "simulated", False) is not True
            or getattr(wire, "simulated", False) is not True
        ):
            raise Failure(Code.OFFLINE_ONLY)
        self.resolver, self.wire, self.credential, self.clock = (
            resolver,
            wire,
            credential,
            clock,
        )
        self._requests = 0
        self._second_authorized = False
        self._max_pages = MAX_REQUESTS
        self._authorization = None

    @classmethod
    def authorized_query(cls, authorization, resolver, wire):
        from .authorization import QueryAuthorization
        from .native import NativeResolver, require_grant
        from .wire import PinnedGetWire

        if (
            type(authorization) is not QueryAuthorization
            or type(resolver) is not NativeResolver
            or type(wire) is not PinnedGetWire
            or wire.simulated is not False
            or resolver.grant is not authorization
            or wire.authorization is not authorization
        ):
            raise Failure(Code.AUTHORIZATION)
        require_grant(authorization)
        instance = cls.__new__(cls)
        instance.resolver, instance.wire, instance.credential, instance.clock = (
            resolver,
            wire,
            authorization.credential,
            time.monotonic,
        )
        instance._requests, instance._second_authorized = 0, False
        instance._max_pages, instance._authorization = (
            authorization.max_pages,
            authorization,
        )
        return instance

    def _page(self, number):
        if (
            self._requests >= self._max_pages
            or number != self._requests + 1
            or (number == 2 and not self._second_authorized)
        ):
            raise Failure(Code.REQUEST)
        request = Request(page_url(number))
        self._requests += 1  # failures consume budget; there is no retry path
        deadline = self.clock() + MAX_SECONDS
        addresses = public_addresses(self.resolver.resolve(HOST, deadline))
        if self.clock() >= deadline:
            raise Failure(Code.TIME)
        pinned = sorted(addresses)[0]

        def revalidate():
            current = public_addresses(self.resolver.resolve(HOST, deadline))
            if current != addresses:
                raise Failure(Code.REBINDING)
            if self.clock() >= deadline:
                raise Failure(Code.TIME)

        return self.wire.exchange(
            request, pinned, deadline, self.credential, revalidate
        )

    def read(self):
        if self._requests:
            raise Failure(Code.REQUEST)
        try:
            body, digest = self._page(1)
            data = decode(body, sensitive_value=self.credential.value)
            first = pagination(data, 1)
            seen = set()
            rows = candidates(data, 1, seen)
            traces = [{"page": 1, "response_sha256": digest}]
            if first is not None and first.total_pages >= 2 and self._max_pages >= 2:
                self._second_authorized = True
                body, digest = self._page(2)
                data = decode(body, sensitive_value=self.credential.value)
                pagination(data, 2, first)
                rows.extend(candidates(data, 2, seen))
                traces.append({"page": 2, "response_sha256": digest})
            scope = (
                "PAGINATION_UNCONFIRMED"
                if first is None
                else "QUERY_TRUNCATED_AT_"
                + ("TWO" if self._max_pages == 2 else "ONE")
                + "_PAGES"
                if first.total_pages > self._max_pages
                else "FILTERED_QUERY_COMPLETE"
            )
            eligible = [r for r in rows if r["eligible_for_human_review"]]
            if len(eligible) > 1 or scope != "FILTERED_QUERY_COMPLETE":
                for row in eligible:
                    row["blockers"].append(
                        "MULTIPLE_COMPATIBLE_VARIANTS"
                        if len(eligible) > 1
                        else "QUERY_SCOPE_UNCONFIRMED"
                    )
                    row["eligible_for_human_review"] = False
            result = {
                "mode": "SIMULATED_RESPONSES_ONLY",
                "real_requests": 0,
                "simulated_gets": self._requests,
                "query_barcode": BARCODE,
                "scope": scope,
                "pages": traces,
                "candidates": rows,
                "authentic_ecomm_id": None,
                "binding_permitted": False,
                "human_approval_required": True,
                "external_writes": False,
            }
            if self._authorization is not None:
                from .authorization import utcnow

                result.update(
                    mode="AUTHORIZED_PROVIDER_RESPONSE",
                    real_requests=self._requests,
                    origin=page_url(1).split("?", 1)[0],
                    authorized_max_pages=self._max_pages,
                    read_at=utcnow().isoformat(),
                    scope_verification="OWNER_ATTESTED_NOT_SERVER_VERIFIED",
                    scope_evidence_sha256=self._authorization.evidence_sha256,
                    requested_provider_mutations=False,
                    provider_side_effects="NOT_VERIFIED_LOGGING_OR_METERING_POSSIBLE",
                )
                del result["simulated_gets"]
                del result["external_writes"]
            return result
        except Failure:
            raise
        except Exception:
            raise Failure(Code.INTERNAL) from None
