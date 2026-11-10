FROM kiki-tech-integration:local AS installed_python
USER 0:0
WORKDIR /offline-build
COPY prepare_runtime.py ./
# -I -S ignores site packages, application paths and Python environment hooks.
# This stage runs only a stdlib copy operation, never the donor's application.
RUN ["/usr/local/bin/python3.12", "-I", "-S", "/offline-build/prepare_runtime.py"]

FROM scratch
COPY --from=installed_python /offline-python/ /
WORKDIR /reader
COPY --chown=1000:1000 ecomm_reader/ ./ecomm_reader/
COPY --chown=1000:1000 tests/ ./tests/
COPY --chown=1000:1000 entrypoint.py ./
ENV PATH=/usr/local/bin PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 1000:1000
ENTRYPOINT ["/usr/local/bin/python3.12", "-I", "-B", "/reader/entrypoint.py"]
