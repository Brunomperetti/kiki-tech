from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...core.security import (
    SESSION_COOKIE,
    create_session,
    csrf_token,
    require_csrf,
    require_session,
    verify_credentials,
)
from ...database.models import AdminSession
from ...database.session import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


def auth_response(session: AdminSession) -> dict:
    return {
        "authenticated": True,
        "username": get_settings().kiki_admin_username,
        "csrf_token": csrf_token(session.token_hash),
    }


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    if not verify_credentials(payload.username, payload.password):
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    token, session = create_session(db)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=get_settings().session_ttl_hours * 3600,
    )
    return auth_response(session)


@router.get("/me")
def me(session: AdminSession = Depends(require_session)):
    return auth_response(session)


@router.post("/logout")
def logout(
    response: Response,
    session: AdminSession = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    db.delete(session)
    db.commit()
    response.delete_cookie(
        SESSION_COOKIE, httponly=True, secure=True, samesite="none", path="/"
    )
    return {"authenticated": False}
