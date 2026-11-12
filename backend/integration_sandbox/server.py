"""ASGI over a Unix socket only; never exposes a container TCP port."""

import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main():
    from .bootstrap import create_sandbox_app

    from .runtime_supervisor import mode
    flag = Path("/runtime/connections-mode")
    connection_mode = flag.read_text().strip() if flag.exists() else "off"
    if connection_mode not in {"off", "offline-fixtures"}:
        raise RuntimeError("Modo de conexiones aisladas inválido.")
    application = create_sandbox_app(autonomous=mode()=="backend", connections=connection_mode=="offline-fixtures")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import uvicorn

    directory = Path("/runtime")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "KIKI local synthetic only")]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                    x509.DNSName("localhost"),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    (directory / "tls-key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (directory / "tls-key.pem").chmod(0o600)
    (directory / "tls-cert.pem").write_bytes(
        cert.public_bytes(serialization.Encoding.PEM)
    )
    uvicorn.run(
        application,
        uds=str(directory / "api.sock"),
        proxy_headers=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
