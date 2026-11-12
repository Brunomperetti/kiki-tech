from .policy import route_allowed, CSP, preflight


def create_sandbox_app(*, autonomous=False):
    preflight()
    # Import ONLY after configuration, socket guard and database identity checks.
    from argon2 import PasswordHasher
    from cryptography.fernet import Fernet
    from app.core import config
    from .policy import DATABASE_URL

    settings = config.Settings(
        _env_file=None,
        database_url=DATABASE_URL,
        app_name="KIKI — integración sintética",
        enable_api_docs=False,
        kiki_admin_username="operador-prueba",
        kiki_admin_password_hash=PasswordHasher().hash("solo-datos-sinteticos"),
        app_session_secret="local-synthetic-session-secret-2b-only",
        app_encryption_key=Fernet.generate_key().decode(),
        cors_origins="https://127.0.0.1:8443",
        frontend_url="https://127.0.0.1:8443",
        ml_api_url="https://blocked.invalid",
        ml_authorization_url="https://blocked.invalid",
        ml_redirect_uri="",
        ml_client_id="",
        ml_client_secret="",
        ecomm_app_api_token="",
        kiki_refresh_token="",
        kiki_ai_api_key="",
        kiki_ai_enabled=False,
        kiki_document_workspace_enabled=True,
        kiki_channel_workspace_enabled=True,
        kiki_editorial_batches_enabled=True,
        kiki_editorial_executor_enabled=autonomous,
        kiki_editorial_lease_seconds=6,
    )
    # Harness-only binding, before any service imports. Production get_settings is unchanged.
    config.get_settings = lambda: settings
    from app.main import create_app, lifespan as original_lifespan
    from app.database.session import SessionLocal, engine
    from contextlib import asynccontextmanager
    from fastapi.responses import JSONResponse
    from .fixtures import seed
    from .research.storage import initialize as initialize_research
    from .research.routes import router as research_router
    from .proposal_routes import router as proposal_router, editor_router
    from .document_routes import router as document_router
    from .assisted_routes import router as assisted_router
    from .mama_routes import router as mama_router
    from .hileret_routes import router as hileret_router

    application = create_app(settings)
    application.include_router(research_router)
    application.include_router(proposal_router)
    application.include_router(document_router)
    application.include_router(assisted_router)
    application.include_router(mama_router)
    application.include_router(hileret_router)
    # Same contract and service; sandbox-only preconditions precede the old route.
    # Production router, DTO and service remain untouched.
    application.router.routes[0:0] = editor_router.routes

    @asynccontextmanager
    async def synthetic_lifespan(app):
        async with original_lifespan(app):
            seed(SessionLocal, allow_scaled=autonomous)
            initialize_research(engine, SessionLocal)
            # Explicit additive migration ONLY after preflight + verified disposable database.
            from sqlalchemy import inspect, text
            from app.services.documental.migration import UP

            with engine.begin() as connection:
                if not inspect(connection).has_table("kiki_evidence_control"):
                    for statement in UP:
                        connection.execute(text(statement))
            from app.services.editorial_batches.migration import UP as EDITORIAL_UP

            with engine.begin() as connection:
                if not inspect(connection).has_table("kiki_editorial_batches"):
                    for statement in EDITORIAL_UP:
                        connection.execute(text(statement))
            from app.services.editorial_batches.migration_2r import UP as EXECUTOR_UP

            with engine.begin() as connection:
                if not inspect(connection).has_table("kiki_editorial_batch_signals"):
                    for statement in EXECUTOR_UP:
                        connection.execute(text(statement))
            try:
                yield
            finally:
                engine.dispose()

    application.router.lifespan_context = synthetic_lifespan

    @application.middleware("http")
    async def isolation_boundary(request, call_next):
        if not route_allowed(request.method, request.url.path):
            response = JSONResponse(
                status_code=403,
                content={"detail": "Operación deshabilitada en etapa 2B sintética."},
            )
        else:
            try:
                response = await call_next(request)
            except Exception:
                response = JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Backend sintético no disponible; sin fallback."
                    },
                )
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Kiki-Environment"] = "local-synthetic"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return application
