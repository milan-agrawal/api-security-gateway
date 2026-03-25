from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

import jwt
from dotenv import load_dotenv
from fastapi import HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from models import User, UserSession

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY environment variable is not set")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440
ACCESS_COOKIE_NAME = os.getenv("ACCESS_COOKIE_NAME", "asg_access_token")
USER_ACCESS_COOKIE_NAME = os.getenv("USER_ACCESS_COOKIE_NAME", "asg_user_access_token")
ADMIN_ACCESS_COOKIE_NAME = os.getenv("ADMIN_ACCESS_COOKIE_NAME", "asg_admin_access_token")
COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() == "true"
COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "lax").strip().lower() or "lax"


def _get_cookie_name(panel: Optional[str] = None) -> str:
    normalized = (panel or "").strip().lower()
    if normalized == "user":
        return USER_ACCESS_COOKIE_NAME
    if normalized == "admin":
        return ADMIN_ACCESS_COOKIE_NAME
    return ACCESS_COOKIE_NAME


def set_auth_cookie(response: Response, token: str, panel: Optional[str] = None) -> None:
    response.set_cookie(
        key=_get_cookie_name(panel),
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def clear_auth_cookie(response: Response, panel: Optional[str] = None) -> None:
    response.delete_cookie(
        key=_get_cookie_name(panel),
        path="/",
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
    )


def clear_all_auth_cookies(response: Response) -> None:
    clear_auth_cookie(response, None)
    clear_auth_cookie(response, "user")
    clear_auth_cookie(response, "admin")


def extract_access_token(request: Request, authorization: Optional[str] = None, panel: Optional[str] = None) -> str:
    header_value = (authorization or "").strip()
    if header_value.startswith("Bearer "):
        header_token = header_value.split(" ", 1)[1].strip()
        if header_token and header_token.lower() not in {"null", "undefined"}:
            return header_token

    normalized = (panel or "").strip().lower()
    if normalized == "user":
        cookie_names = [USER_ACCESS_COOKIE_NAME, ACCESS_COOKIE_NAME]
    elif normalized == "admin":
        cookie_names = [ADMIN_ACCESS_COOKIE_NAME, ACCESS_COOKIE_NAME]
    elif normalized == "public":
        cookie_names = [ACCESS_COOKIE_NAME]
    else:
        cookie_names = [ACCESS_COOKIE_NAME, USER_ACCESS_COOKIE_NAME, ADMIN_ACCESS_COOKIE_NAME]

    for cookie_name in cookie_names:
        cookie_token = (request.cookies.get(cookie_name) or "").strip()
        if cookie_token:
            return cookie_token

    if authorization and not header_value.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def resolve_user_from_token(
    token: str,
    db: Session,
    *,
    require_admin: bool = False,
    validate_session: bool = True,
) -> User:
    payload = decode_access_token(token)
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is no longer valid for this account")

    if getattr(user, "token_version", 0) != payload.get("token_version", 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

    if require_admin and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    session_id = payload.get("session_id")
    if validate_session and session_id:
        session = db.query(UserSession).filter(
            UserSession.session_token == session_id,
            UserSession.user_id == user.id,
        ).first()
        if not session or session.is_revoked:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")

        now = datetime.utcnow()
        if not session.last_active_at or (now - session.last_active_at).total_seconds() > 60:
            session.last_active_at = now
            db.commit()
        user._current_session_id = session_id
    else:
        user._current_session_id = session_id

    return user


def resolve_user_from_request(
    request: Request,
    db: Session,
    authorization: Optional[str] = None,
    *,
    panel: Optional[str] = None,
    require_admin: bool = False,
    validate_session: bool = True,
) -> User:
    token = extract_access_token(request, authorization, panel=panel)
    return resolve_user_from_token(
        token,
        db,
        require_admin=require_admin,
        validate_session=validate_session,
    )
