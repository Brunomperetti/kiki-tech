from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .api.routes.catalog import router
from .api.routes.mercadolibre import router as mercadolibre_router
from .api.routes.auth import router as auth_router
from .api.routes.prepublication import router as prepublication_router
from .core.config import get_settings
from .core.logging import configure_logging
from .database.models import Base
from .database.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    Base.metadata.create_all(engine)
    yield


def create_app(settings=None) -> FastAPI:
    settings = settings or get_settings()
    docs_enabled = settings.enable_api_docs
    application = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[x.strip() for x in settings.cors_origins.split(",")],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    application.include_router(router)
    application.include_router(mercadolibre_router)
    application.include_router(auth_router)
    application.include_router(prepublication_router)

    @application.get("/health")
    def health():
        return {"status": "ok", "mode": "read-only-external-systems"}

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"detail": "Ocurrió un error inesperado. Intentá nuevamente."},
        )

    return application


app = create_app()
