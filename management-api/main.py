from fastapi import FastAPI, Depends, HTTPException, status, Request, BackgroundTasks, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from typing import Optional
import asyncio
import jwt
import os
import uuid
import secrets
import logging

from db import engine, Base
from models import User, UserSession, AuditLog
from deps import get_db
from admin import router as admin_router
from auth.mfa import router as mfa_router, create_mfa_temp_token
from auth.session_auth import (
    clear_auth_cookie,
    clear_all_auth_cookies,
    extract_access_token,
    resolve_user_from_request,
    resolve_user_from_token,
    set_auth_cookie,
)
from auth.password_reset import router as password_reset_router
from user import router as user_router
from utils import (
    parse_user_agent,
    log_audit,
    get_ip_location,
    evaluate_geo_policy,
    send_new_login_alert_email,
    send_failed_login_attempts_alert,
    send_weekly_security_digest_email,
)
from db import SessionLocal

logger = logging.getLogger(__name__)
PANEL_HANDOFF_TTL_SECONDS = 60
PANEL_HANDOFFS: dict[str, dict] = {}

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Management API", version="1.0.0")

# Include routers
app.include_router(admin_router)
app.include_router(mfa_router)
app.include_router(password_reset_router)
app.include_router(user_router)

# CORS middleware - Restrict to specific origins
ALLOWED_ORIGINS = [
    "http://localhost:3000",  # Public App
    "http://localhost:3001",  # User Panel  
    "http://localhost:3002",  # Admin Panel
    # Add production URLs here when deploying
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # ✅ Specific origins only
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],  # Include OPTIONS for preflight
    allow_headers=["*"],  # Allow all headers for preflight compatibility
)


async def _weekly_digest_scheduler():
    while True:
        try:
            _run_weekly_digest_cycle()
        except Exception as exc:
            logger.warning("Weekly digest worker error: %s", exc)
        await asyncio.sleep(3600)


def _run_weekly_digest_cycle():
    now = datetime.utcnow()
    if now.weekday() != 0:
        return

    week_start = now - timedelta(days=7)
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.weekly_security_digest_enabled == True).all()
        for user in users:
            if user.last_weekly_digest_sent_at and (now - user.last_weekly_digest_sent_at) < timedelta(days=7):
                continue

            events = db.query(AuditLog).filter(
                AuditLog.user_id == user.id,
                AuditLog.created_at >= week_start
            ).all()

            active_sessions = db.query(UserSession).filter(
                UserSession.user_id == user.id,
                UserSession.is_revoked == False
            ).count()

            summary = {
                "logins": sum(1 for e in events if e.event_type == "login"),
                "login_failed": sum(1 for e in events if e.event_type == "login_failed"),
                "login_blocked_geo": sum(1 for e in events if e.event_type == "login_blocked_geo"),
                "password_changed": sum(1 for e in events if e.event_type == "password_changed"),
                "mfa_changes": sum(1 for e in events if e.event_type in ("mfa_enabled", "mfa_disabled")),
                "active_sessions": active_sessions,
            }

            if send_weekly_security_digest_email(user.email, user.full_name, summary):
                user.last_weekly_digest_sent_at = now
                db.commit()
    finally:
        db.close()


@app.on_event("startup")
async def startup_digest_worker():
    app.state.weekly_digest_task = asyncio.create_task(_weekly_digest_scheduler())


@app.on_event("shutdown")
async def shutdown_digest_worker():
    task = getattr(app.state, "weekly_digest_task", None)
    if task:
        task.cancel()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings - Require SECRET_KEY to be set
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY environment variable is not set. "
        "Please set it in .env file for security."
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

# Request/Response models
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    token: Optional[str] = None
    email: str
    role: str
    full_name: str
    # MFA fields
    mfa_required: bool = False
    mfa_setup_required: bool = False
    temp_token: Optional[str] = None


class PanelHandoffCreateRequest(BaseModel):
    target_panel: str


class PanelHandoffCreateResponse(BaseModel):
    handoff_code: str
    expires_in_seconds: int


class PanelHandoffExchangeRequest(BaseModel):
    handoff_code: str


class PanelHandoffExchangeResponse(BaseModel):
    token: Optional[str] = None
    email: str
    role: str
    full_name: str


class SessionUserResponse(BaseModel):
    email: str
    role: str
    full_name: str


def _normalize_panel(panel: Optional[str]) -> str:
    normalized = (panel or "").strip().lower()
    return normalized if normalized in {"user", "admin", "public"} else ""

# Helper functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, token_version: int = 0, session_id: str = None) -> str:
    """Create JWT access token and include token_version for session invalidation."""
    to_encode = data.copy()
    to_encode.update({"token_version": token_version})
    if session_id:
        to_encode["session_id"] = session_id
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def _prune_panel_handoffs():
    now = datetime.utcnow()
    expired_codes = [code for code, item in PANEL_HANDOFFS.items() if item.get("expires_at") <= now]
    for code in expired_codes:
        PANEL_HANDOFFS.pop(code, None)


# Routes
@app.get("/")
def root():
    return {
        "service": "Management API",
        "version": "1.0.0",
        "status": "running"
    }


@app.post("/auth/panel-handoff", response_model=PanelHandoffCreateResponse)
def create_panel_handoff(
    body: PanelHandoffCreateRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    _prune_panel_handoffs()
    token = extract_access_token(request, authorization, panel="public")
    user = resolve_user_from_token(token, db)

    target_panel = (body.target_panel or "").strip().lower()
    if target_panel not in {"user", "admin"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid target panel")
    if target_panel == "admin" and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    handoff_code = secrets.token_urlsafe(24)
    PANEL_HANDOFFS[handoff_code] = {
        "token": token,
        "email": user.email,
        "role": user.role,
        "full_name": user.full_name,
        "target_panel": target_panel,
        "expires_at": datetime.utcnow() + timedelta(seconds=PANEL_HANDOFF_TTL_SECONDS),
    }
    return PanelHandoffCreateResponse(
        handoff_code=handoff_code,
        expires_in_seconds=PANEL_HANDOFF_TTL_SECONDS,
    )


@app.post("/auth/panel-handoff/exchange", response_model=PanelHandoffExchangeResponse)
def exchange_panel_handoff(body: PanelHandoffExchangeRequest, response: Response):
    _prune_panel_handoffs()
    handoff_code = (body.handoff_code or "").strip()
    payload = PANEL_HANDOFFS.pop(handoff_code, None)
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired handoff code")

    set_auth_cookie(response, payload["token"], panel=payload.get("target_panel"))
    clear_auth_cookie(response, panel="public")
    return PanelHandoffExchangeResponse(
        token=None,
        email=payload["email"],
        role=payload["role"],
        full_name=payload["full_name"],
    )


@app.get("/auth/me", response_model=SessionUserResponse)
def get_session_user(
    request: Request,
    panel: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    user = resolve_user_from_request(request, db, authorization, panel=_normalize_panel(panel))
    return SessionUserResponse(
        email=user.email,
        role=user.role,
        full_name=user.full_name,
    )


@app.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    panel: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    normalized_panel = _normalize_panel(panel)
    try:
        token = extract_access_token(request, authorization, panel=normalized_panel or None)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = resolve_user_from_token(token, db)
        session_id = payload.get("session_id")
        if session_id:
            session = db.query(UserSession).filter(
                UserSession.session_token == session_id,
                UserSession.user_id == user.id,
            ).first()
            if session and not session.is_revoked:
                session.is_revoked = True
                session.revoked_at = datetime.utcnow()
                db.commit()
    except HTTPException:
        pass
    except jwt.InvalidTokenError:
        pass

    if normalized_panel:
        clear_auth_cookie(response, panel=normalized_panel if normalized_panel != "public" else None)
    else:
        clear_all_auth_cookies(response)
    return {"success": True, "message": "Logged out"}

@app.post("/auth/login", response_model=LoginResponse)
def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Authenticate user and return JWT token.
    If MFA is enabled, returns temp_token instead for MFA verification.
    """
    # Find user by email
    user = db.query(User).filter(User.email == credentials.email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Check account lockout
    if user.locked_until and user.locked_until > datetime.utcnow():
        mins_left = int((user.locked_until - datetime.utcnow()).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account locked due to too many failed attempts. Try again in {mins_left} minute(s)."
        )
    
    # Verify password
    if not verify_password(credentials.password, user.password_hash):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        attempts = user.failed_login_attempts
        # Lock after 5 consecutive failures
        if attempts >= 5:
            user.locked_until = datetime.utcnow() + timedelta(minutes=15)
            log_audit(db, user.id, "login_failed", f"Account locked after {attempts} failed attempts", request)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed attempts. Your account has been locked for 15 minutes."
            )
        log_audit(db, user.id, "login_failed", "Invalid password", request)
        db.commit()
        if attempts == 3 and user.failed_login_alert_enabled:
            client_ip = request.client.host if request.client else "unknown"
            background_tasks.add_task(
                send_failed_login_attempts_alert,
                recipient_email=user.email,
                full_name=user.full_name,
                attempts=attempts,
                ip_address=client_ip,
            )
        remaining = 5 - attempts
        if remaining <= 2:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid email or password. Warning: {remaining} attempt(s) remaining before account lockout."
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Reset failed attempts on success
    if user.failed_login_attempts:
        user.failed_login_attempts = 0
        user.locked_until = None
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled"
        )
    
    client_ip = request.client.host if request.client else "unknown"
    
    # 🌍 Geo-fencing & New Location Detection
    location = get_ip_location(client_ip, db)
    country = None
    city = None
    is_new = False
    
    if location:
        country = location.get("country")
        city = location.get("city")
        if country and country != "Local Network":
            existing = db.query(UserSession).filter(
                UserSession.user_id == user.id,
                UserSession.country == country
            ).first()
            if not existing:
                is_new = True

    geo_policy = evaluate_geo_policy(user.allowed_countries, location)
    if not geo_policy["allowed"]:
        resolved_country = geo_policy["country"] or "Unknown"
        policy_text = geo_policy["policy"] or "Global"
        log_audit(
            db,
            user.id,
            "login_blocked_geo",
            f"Blocked login from {resolved_country} ({client_ip}). Policy: {policy_text}. Reason: {geo_policy['reason']}",
            request,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=geo_policy["detail"]
        )

    # Check if MFA is enabled
    if user.mfa_enabled:
        # Generate temporary token for MFA verification
        temp_token = create_mfa_temp_token(user.email, user.id)
        
        return LoginResponse(
            token=None,
            email=user.email,
            role=user.role,
            full_name=user.full_name,
            mfa_required=True,
            mfa_setup_required=not user.mfa_setup_complete,
            temp_token=temp_token
        )
    
    # Create session record
    ua_string = request.headers.get("user-agent", "")
    session_id = str(uuid.uuid4())

    # Cleanup: purge revoked sessions older than 30 days
    cutoff = datetime.utcnow() - timedelta(days=30)
    db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.is_revoked == True,
        UserSession.created_at < cutoff
    ).delete(synchronize_session=False)

    session = UserSession(
        user_id=user.id,
        session_token=session_id,
        ip_address=client_ip,
        user_agent=ua_string,
        device_label=parse_user_agent(ua_string),
        country=country,
        city=city,
        is_new_location=is_new,
        created_at=datetime.utcnow(),
        last_active_at=datetime.utcnow(),
    )
    db.add(session)

    # No MFA - create full JWT token
    token_data = {
        "sub": user.email,
        "role": user.role,
        "user_id": user.id
    }
    token = create_access_token(token_data, token_version=user.token_version, session_id=session_id)
    
    # Update last login timestamp
    user.last_login_at = datetime.now(timezone.utc)
    log_audit(db, user.id, "login", "Login successful", request)
    db.commit()

    if user.new_login_alert_enabled:
        location_label = "Local Network" if country == "Local Network" else ", ".join(
            [part for part in [city, country] if part]
        ) or "Unknown location"
        background_tasks.add_task(
            send_new_login_alert_email,
            recipient_email=user.email,
            full_name=user.full_name,
            device_label=session.device_label,
            ip_address=client_ip,
            location_label=location_label,
        )
    
    set_auth_cookie(response, token)

    return LoginResponse(
        token=None,
        email=user.email,
        role=user.role,
        full_name=user.full_name,
        mfa_required=False,
        mfa_setup_required=False,
        temp_token=None
    )

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
