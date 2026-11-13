"""Pinned native HTTPS, prepared for a separately authorized direct deployment.

Managed Cloud/proxy routes fail closed: no direct-network workaround is provided.
All native primitives are replaceable in offline tests, not through CLI options.
"""

import os
from pathlib import Path
import queue
import socket
import threading
import time

from .authorization import QueryAuthorization
from .policy import (
    HOST,
    Request,
    page_url,
    public_addresses,
    strict_context,
    check_context,
)
from .safety import Code, Failure, native_call
from .wire import PinnedGetWire, get_bytes, remaining, peer

PROXY_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def require_direct_environment():
    # A CONNECT proxy hides the origin peer/DNS from this pinned TCP transport.
    # Never clear a Cloud proxy, use NO_PROXY, or connect directly around policy.
    if (
        Path("/etc/codex").exists()
        or Path("/opt/codex").exists()
        or any(k.startswith("CODEX_") for k in os.environ)
        or any(os.environ.get(k) for k in PROXY_KEYS)
    ):
        raise Failure(Code.ENVIRONMENT)


def require_grant(grant):
    if type(grant) is not QueryAuthorization:
        raise Failure(Code.AUTHORIZATION)
    grant.validate()
    require_direct_environment()


class NativeResolver:
    simulated = False

    def __init__(self, grant, *, lookup=None, clock=time.monotonic):
        require_grant(grant)
        self.grant = grant
        self.lookup = lookup if lookup is not None else socket.getaddrinfo
        self.clock = clock

    def resolve(self, host, deadline):
        require_grant(self.grant)
        if host != HOST:
            raise Failure(Code.DNS)
        remaining(deadline, self.clock)
        result = queue.Queue(maxsize=1)

        def resolve_once():
            try:
                with native_call(self.grant, "dns"):
                    rows = self.lookup(
                        HOST,
                        443,
                        socket.AF_UNSPEC,
                        socket.SOCK_STREAM,
                        socket.IPPROTO_TCP,
                        0,
                    )
                addresses = []
                if not isinstance(rows, list) or not 1 <= len(rows) <= 16:
                    raise Failure(Code.DNS)
                for family, kind, proto, _, address in rows:
                    if (
                        family not in (socket.AF_INET, socket.AF_INET6)
                        or kind != socket.SOCK_STREAM
                        or proto != socket.IPPROTO_TCP
                        or address[1] != 443
                        or (
                            family == socket.AF_INET6
                            and (len(address) != 4 or address[2:] != (0, 0))
                        )
                    ):
                        raise Failure(Code.DNS)
                    addresses.append(address[0])
                result.put((True, tuple(sorted(public_addresses(addresses)))))
            except Exception as exc:
                result.put((False, exc.code if isinstance(exc, Failure) else Code.DNS))

        # getaddrinfo has no Python timeout. A bounded daemon worker prevents it
        # holding up the query; the standalone process exits on failure, no retry.
        threading.Thread(target=resolve_once, daemon=True).start()
        try:
            ok, value = result.get(timeout=remaining(deadline, self.clock))
        except queue.Empty:
            raise Failure(Code.TIME) from None
        remaining(deadline, self.clock)
        if not ok:
            raise Failure(value)
        return value


class NativeChannel:
    def __init__(self, raw, pinned, grant, *, tls_verified=False):
        self.raw, self.pinned, self.grant = raw, pinned, grant
        self.sent = False
        self.tls_verified = tls_verified

    def connect(self, address):
        if address != (self.pinned, 443):
            raise Failure(Code.DNS)
        target = address if self.raw.family == socket.AF_INET else (*address, 0, 0)
        with native_call(self.grant, "connect", channel=self.raw, address=target):
            self.raw.connect(target)

    def settimeout(self, value):
        self.raw.settimeout(value)

    def getpeername(self):
        return self.raw.getpeername()

    def getpeercert(self):
        return self.raw.getpeercert()

    def sendall(self, data):
        require_grant(self.grant)
        if not self.tls_verified:
            raise Failure(Code.TLS)
        permitted = [
            get_bytes(Request(page_url(p)), self.grant.credential)
            for p in range(1, self.grant.max_pages + 1)
        ]
        if self.sent or data not in permitted:
            raise Failure(Code.REQUEST)
        self.sent = True  # no second write, retry or body on this connection
        self.raw.sendall(data)

    def recv(self, count):
        return self.raw.recv(count)

    def close(self):
        self.raw.close()


class NativeSocketFactory:
    simulated = False

    def __init__(self, grant, *, driver=None):
        require_grant(grant)
        self.grant, self.driver = grant, driver if driver is not None else socket
        self.opened = 0

    def open(self, pinned):
        require_grant(self.grant)
        public_addresses([pinned])
        if self.opened >= self.grant.max_pages:
            raise Failure(Code.REQUEST)
        self.opened += 1
        family = socket.AF_INET6 if ":" in pinned else socket.AF_INET
        with native_call(self.grant, "open", family=family):
            raw = self.driver.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        return NativeChannel(raw, pinned, self.grant)


class NativeTlsContext:
    def __init__(self, grant, context):
        self.grant, self.context = grant, context

    def __getattr__(self, name):
        return getattr(self.context, name)

    def wrap_socket(self, channel, server_hostname):
        require_grant(self.grant)
        if (
            type(channel) is not NativeChannel
            or channel.grant is not self.grant
            or server_hostname != HOST
        ):
            raise Failure(Code.TLS)
        check_context(self.context)
        wrapped = None
        try:
            with native_call(
                self.grant, "tls", channel=channel.raw, family=channel.raw.family
            ):
                wrapped = self.context.wrap_socket(channel.raw, server_hostname=HOST)
            check_context(self.context)
            peer(wrapped, channel.pinned)
            if not wrapped.getpeercert():
                raise Failure(Code.TLS)
            return NativeChannel(wrapped, channel.pinned, self.grant, tls_verified=True)
        except Exception:
            if wrapped is not None:
                wrapped.close()
            raise


def prepare(grant, *, driver=None, lookup=None, context=None):
    """Construct adapter; does not resolve/connect/send until reader.read().

    Injection is for unit tests. The executable never accepts driver/lookup/CA
    overrides, arbitrary URLs or methods.
    """
    require_grant(grant)
    factory = NativeSocketFactory(grant, driver=driver)
    tls = NativeTlsContext(grant, context if context is not None else strict_context())
    wire = PinnedGetWire(socket_factory=factory, context=tls, authorization=grant)
    return NativeResolver(grant, lookup=lookup), wire
