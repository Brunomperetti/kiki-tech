"""Local doubles only. The fixture IDs are NOT Hileret's authentic Ecomm IDs."""

from copy import deepcopy
import json
import ssl
from .policy import HOST
from .reader import InventoryReader
from .wire import Credential, PinnedGetWire


class FakeDNS:
    simulated = True

    def __init__(self, answers=None):
        self.answers = answers or [("8.8.8.8",)]
        self.calls = []

    def resolve(self, host, deadline):
        self.calls.append(host)
        return self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]


class FakeSocket:
    def __init__(
        self, response, *, tcp_peer=None, tls_peer=None, final_peer=None, port=443
    ):
        self.response = response
        self.tcp_peer, self.tls_peer, self.final_peer = tcp_peer, tls_peer, final_peer
        self.port = port
        self.address = None
        self.tls = False
        self.sent = b""
        self.timeouts = []
        self.closed = False

    def connect(self, address):
        self.address = address  # memory only; no socket or DNS implementation exists

    def settimeout(self, value):
        self.timeouts.append(value)

    def getpeername(self):
        actual = (
            self.final_peer
            if not self.response and self.final_peer
            else self.tls_peer
            if self.tls
            else self.tcp_peer
        )
        return actual or self.address[0], self.port

    def getpeercert(self):
        return {"subjectAltName": (("DNS", HOST),)}

    def sendall(self, value):
        self.sent += value

    def recv(self, count):
        result, self.response = self.response[:count], self.response[count:]
        return result

    def close(self):
        self.closed = True


class FakeContext:
    check_hostname = True
    verify_mode = ssl.CERT_REQUIRED
    minimum_version = ssl.TLSVersion.TLSv1_2
    keylog_filename = None

    def __init__(self, *, fail=False):
        self.fail = fail
        self.sni = []

    def wrap_socket(self, channel, server_hostname):
        self.sni.append(server_hostname)
        if self.fail:
            raise ssl.SSLCertVerificationError("SIMULATED UNTRUSTED CERTIFICATE")
        channel.tls = True
        return channel


def http_reply(data=None, *, body=None, status=200, headers=None):
    body = body if body is not None else json.dumps(data, ensure_ascii=False).encode()
    fields = (
        headers
        if headers is not None
        else [("Content-Type", "application/json"), ("Content-Length", str(len(body)))]
    )
    head = (
        f"HTTP/1.1 {status} SIMULATED\r\n"
        + "".join(f"{k}: {v}\r\n" for k, v in fields)
        + "\r\n"
    )
    return head.encode("ascii") + body


class FakeFactory:
    simulated = True

    def __init__(self, replies, **socket_options):
        self.replies = list(replies)
        self.socket_options = socket_options
        self.channels = []

    def __call__(self):
        result = FakeSocket(self.replies.pop(0), **self.socket_options)
        self.channels.append(result)
        return result


def item(
    ident=900001,
    *,
    description="Unidad de 200 ml",
    combo=False,
    brand="Hileret",
    barcode="7794940000796",
    gtin="7794940000796",
):
    return {
        "code": "SIMULATED-PARENT-NOT-A-MASTER-RECORD",
        "description": "Hileret Stevia",
        "variants": [
            {
                "id": ident,
                "sku": "SIMULATED-SKU-NOT-CLIENT-DATA",
                "brand": brand,
                "variant_description": description,
                "is_combo": combo,
                "barcode": barcode,
                "gtin": gtin,
            }
        ],
    }


def envelope(items=None, *, page=1, total=1):
    return {
        "data": {
            "items": deepcopy(items if items is not None else [item()]),
            "paginacion": {
                "page": page,
                "total": total,
                "per_page": 50,
                "total_pages": (total + 49) // 50,
            },
        }
    }


def demo_reader():
    factory = FakeFactory(
        [
            http_reply(
                envelope(
                    [
                        item(),
                        item(900002, description="Pack x6 de 200 ml", combo=True),
                        item(900003, description="Caja 9 x 200 ml", combo=True),
                    ],
                    total=3,
                )
            )
        ]
    )
    wire = PinnedGetWire(socket_factory=factory, context=FakeContext())
    return InventoryReader(FakeDNS(), wire, Credential("OFFLINE-NON-SECRET-FIXTURE"))
