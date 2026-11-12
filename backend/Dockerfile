# One image/service; reader root has no backend, .env, /proc or mounted secrets.
FROM python:3.12-slim-bookworm AS reader
COPY requirements-reader.txt /requirements-reader.txt
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r /requirements-reader.txt; else pip install --no-cache-dir -r /requirements-reader.txt; fi && \
    mkdir -p /reader-root/usr /reader-root/lib /reader-root/lib64 /reader-root/run && \
    cp -a /usr/local /reader-root/usr/local && cp -a /lib/. /reader-root/lib/ && cp -a /lib64/. /reader-root/lib64/
COPY --chmod=755 document_reader /reader-root/usr/local/lib/python3.12/site-packages/document_reader

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements.txt; else pip install --no-cache-dir -r requirements.txt; fi
COPY --from=reader /reader-root /opt/kiki-reader
COPY --chmod=755 . .
RUN chown 10001:10000 /opt/kiki-reader/run && chmod 0750 /opt/kiki-reader/run
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 KIKI_DOCUMENT_PARSER_KERNEL_REQUIRED=true KIKI_AUTO_CREATE_SCHEMA=false KIKI_DOCUMENT_PARSER_SOCKET=/opt/kiki-reader/run/parser.sock
EXPOSE 8000
CMD ["python","/app/start.py"]
