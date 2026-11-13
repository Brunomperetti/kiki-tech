from dataclasses import dataclass
import ipaddress
import ssl
from urllib.parse import urlsplit
from .safety import Code, Failure

HOST = "admin.ecomm-app.com"
PATH = "/api/v3/public/inventario/productos"
BARCODE = "7794940000796"
PAGE_SIZE = 50
MAX_BYTES = 2 * 1024 * 1024
MAX_SECONDS = 12
MAX_REQUESTS = 2


def page_url(page):
    if type(page) is not int or page not in (1, 2):
        raise Failure(Code.REQUEST)
    return f"https://{HOST}{PATH}?barcode={BARCODE}&page={page}&limit=50&sort=sku_asc"


@dataclass(frozen=True)
class Request:
    url: str
    method: str = "GET"


def checked_request(request):
    try:
        if request.method != "GET" or not isinstance(request.url, str):
            raise Failure(Code.REQUEST)
        p = urlsplit(request.url)
        if (
            p.scheme != "https"
            or p.netloc != HOST
            or p.path != PATH
            or p.fragment
            or p.username
            or p.password
            or request.url not in (page_url(1), page_url(2))
        ):
            raise Failure(Code.REQUEST)
        return p
    except (ValueError, AttributeError):
        raise Failure(Code.REQUEST) from None


def public_addresses(values):
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 16:
        raise Failure(Code.DNS)
    result = set()
    for value in values:
        try:
            if not isinstance(value, str) or "%" in value or value.strip() != value:
                raise ValueError
            address = ipaddress.ip_address(value)
            if (
                not address.is_global
                or address.is_private
                or address.is_reserved
                or address.is_multicast
                or address.is_unspecified
                or address.is_loopback
                or address.is_link_local
                or getattr(address, "ipv4_mapped", None)
            ):
                raise ValueError
            result.add(str(address))
        except ValueError:
            raise Failure(Code.DNS) from None
    return frozenset(result)


def strict_context():
    # Explicit OS trust: no .env, custom provider key, SSLKEYLOGFILE or insecure TLS.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cafile="/etc/ssl/certs/ca-certificates.crt")
    check_context(context)
    return context


def check_context(context):
    if (
        not context.check_hostname
        or context.verify_mode != ssl.CERT_REQUIRED
        or context.minimum_version < ssl.TLSVersion.TLSv1_2
        or getattr(context, "keylog_filename", None)
    ):
        raise Failure(Code.TLS)
