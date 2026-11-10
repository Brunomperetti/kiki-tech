from .policy import route_allowed, CSP, preflight


def create_sandbox_app():
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

    application = create_app(settings)
    application.include_router(research_router)

    @asynccontextmanager
    async def synthetic_lifespan(app):
        async with original_lifespan(app):
            seed(SessionLocal)
            initialize_research(engine, SessionLocal)
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
