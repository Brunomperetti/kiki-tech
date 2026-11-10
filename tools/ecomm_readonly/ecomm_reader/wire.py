"""Actual HTTP GET codec exercised only with injected offline TLS/socket doubles.

No system socket factory, URL opener, redirects, cookie jar or real resolver.
"""

from dataclasses import dataclass, field
import hashlib
import http.client
import io
import time
from .policy import (
    HOST,
    MAX_BYTES,
    checked_request,
    check_context,
    strict_context,
    public_addresses,
)
from .safety import Code, Failure


@dataclass(frozen=True)
class Credential:
    value: str = field(repr=False)

    def __post_init__(self):
        if (
            not isinstance(self.value, str)
            or not 1 <= len(self.value) <= 4096
            or not self.value.isascii()
            or any(ord(c) <= 32 or ord(c) == 127 for c in self.value)
        ):
            raise Failure(Code.CREDENTIAL)


def remaining(deadline, clock):
    result = deadline - clock()
    if result <= 0:
        raise Failure(Code.TIME)
    return result


class DeadlineStream(io.RawIOBase):
    def __init__(self, channel, deadline, clock):
        self.channel, self.deadline, self.clock = channel, deadline, clock
        self.received = 0

    def readable(self):
        return True

    def readinto(self, buffer):
        self.channel.settimeout(remaining(self.deadline, self.clock))
        data = self.channel.recv(len(buffer))
        self.received += len(data)
        if self.received > MAX_BYTES + 32768:
            raise Failure(Code.LIMIT)
        buffer[: len(data)] = data
        return len(data)


def peer(channel, pinned):
    value = channel.getpeername()
    if value[0] != pinned or value[1] != 443:
        raise Failure(Code.TLS)


class PinnedGetWire:
    simulated = True

    def __init__(self, *, socket_factory=None, context=None, clock=time.monotonic):
        if (
            socket_factory is None
            or getattr(socket_factory, "simulated", False) is not True
        ):
            raise Failure(Code.OFFLINE_ONLY)
        self.factory = socket_factory
        self.context = context if context is not None else strict_context()
        check_context(self.context)
        self.clock = clock

    def exchange(self, request, pinned, deadline, credential, revalidate_dns):
        checked_request(request)
        public_addresses([pinned])
        check_context(self.context)
        channel = tls = response = None
        try:
            remaining(deadline, self.clock)
            channel = self.factory()
            channel.settimeout(remaining(deadline, self.clock))
            channel.connect((pinned, 443))  # numeric pinned destination, not DNS again
            peer(channel, pinned)
            channel.settimeout(remaining(deadline, self.clock))
            tls = self.context.wrap_socket(channel, server_hostname=HOST)
            check_context(self.context)
            peer(tls, pinned)
            if not tls.getpeercert():
                raise Failure(Code.TLS)
            revalidate_dns()  # must still match the original public DNS set BEFORE bearer
            peer(tls, pinned)
            target = request.url.split(HOST, 1)[1]
            headers = (
                f"GET {target} HTTP/1.1\r\nHost: {HOST}\r\n"
                "Accept: application/json\r\nAccept-Encoding: identity\r\n"
                "Connection: close\r\nAuthorization: Bearer "
                + credential.value
                + "\r\n\r\n"
            )
            tls.settimeout(remaining(deadline, self.clock))
            tls.sendall(headers.encode("ascii"))
            stream = io.BufferedReader(DeadlineStream(tls, deadline, self.clock), 4096)

            class ResponseSocket:
                def makefile(self, mode):
                    return stream

            response = http.client.HTTPResponse(ResponseSocket())
            response.begin()  # codec has NO redirect-following implementation
            remaining(deadline, self.clock)
            if (
                300 <= response.status <= 399
                or response.headers.get("Location") is not None
            ):
                raise Failure(Code.REDIRECT)
            if response.status != 200:
                raise Failure(Code.HTTP)
            headers = response.headers
            if sum(len(k) + len(v) for k, v in headers.items()) > 16384:
                raise Failure(Code.LIMIT)
            if any(
                len(headers.get_all(k, [])) > 1
                for k in (
                    "Content-Length",
                    "Content-Type",
                    "Content-Encoding",
                    "Transfer-Encoding",
                )
            ):
                raise Failure(Code.HTTP)
            if (
                headers.get_content_type() != "application/json"
                or headers.get_content_charset() not in (None, "utf-8")
                or headers.get("Content-Encoding", "identity").lower() != "identity"
                or headers.get("Transfer-Encoding", "chunked").lower() != "chunked"
                or (headers.get("Transfer-Encoding") and headers.get("Content-Length"))
            ):
                raise Failure(Code.HTTP)
            length = headers.get("Content-Length")
            if length is not None and (
                not length.isascii()
                or not length.isdecimal()
                or int(length) > MAX_BYTES
            ):
                raise Failure(Code.LIMIT)
            body = bytearray()
            while True:
                remaining(deadline, self.clock)
                peer(tls, pinned)
                chunk = response.read(min(65536, MAX_BYTES + 1 - len(body)))
                remaining(deadline, self.clock)
                if not chunk:
                    break
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    raise Failure(Code.LIMIT)
            peer(tls, pinned)
            if length is not None and len(body) != int(length):
                raise Failure(Code.HTTP)
            if credential.value.encode("ascii") in body:
                raise Failure(Code.SECRET)
            return bytes(body), hashlib.sha256(body).hexdigest()
        except Failure:
            raise
        except TimeoutError:
            raise Failure(Code.TIME) from None
        except http.client.HTTPException:
            raise Failure(Code.HTTP) from None
        except Exception:
            # TLS/socket/HTTP exceptions can echo headers or provider text.
            raise Failure(Code.TLS) from None
        finally:
            for value in (response, tls, channel):
                if value is not None:
                    try:
                        value.close()
                    except Exception:
                        pass
