# Dependencies are installed only during build. Runtime containers have no network.
FROM python:3.12-slim-bookworm
WORKDIR /sandbox
COPY backend/requirements.txt backend/requirements-dev.txt ./
COPY backend/integration_sandbox/requirements-documents.txt ./requirements-documents.txt
RUN --mount=type=secret,id=proxy_ca,required=true \
    PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements-dev.txt -r requirements-documents.txt
# The Dockerfile-specific context allowlist includes only source/tests/requirements.
COPY --chown=1000:1000 backend/ ./
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 1000:1000
CMD ["python", "-m", "integration_sandbox.server"]
