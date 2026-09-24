from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .api.routes.catalog import router
from .core.config import get_settings
from .core.logging import configure_logging
from .database.models import Base
from .database.session import engine
@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(); Base.metadata.create_all(engine); yield
settings=get_settings(); app=FastAPI(title=settings.app_name,version="1.0.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.cors_origins.split(",")],allow_methods=["GET","POST"],allow_headers=["*"])
app.include_router(router)
@app.get("/health")
def health(): return {"status":"ok","mode":"read-only-external-systems"}
@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    return JSONResponse(status_code=500,content={"detail":"Ocurrió un error inesperado. Intentá nuevamente."})
