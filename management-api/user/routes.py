"""
User Self-Service Routes
========================
Endpoints for the user panel — users manage their own profile, password, etc.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from typing import Optional
from datetime import datetime, timezone
import jwt
import os
import re
import json

from deps import get_db
from models import User, APIKey, UserSession
from utils import (
    generate_mfa_secret,
    generate_qr_code_base64,
    verify_totp,
    generate_backup_codes,
    encrypt_secret,
    decrypt_secret,
    log_audit,
    normalize_allowed_countries,
    send_password_changed_notification,
    send_mfa_change_notification,
)

router = APIRouter(prefix="/user", tags=["User Self-Service"])

# Password hashing (same config as main.py)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"


# ============================================================================
# Auth Dependency
# ============================================================================

def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """Extract and verify user from JWT token."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing"
        )
    try:
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format"
            )
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        # Enforce token_version for session invalidation
        token_version = payload.get("token_version", 0)
        if getattr(user, "token_version", 0) != token_version:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked"
            )
        # Validate session if session_id is in token
        session_id = payload.get("session_id")
        if session_id:
            session = db.query(UserSession).filter(
                UserSession.session_token == session_id,
                UserSession.user_id == user.id
            ).first()
            if not session or session.is_revoked:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session has been revoked"
                )
            # Update last_active_at (throttled: only if > 1 minute since last update)
            now = datetime.utcnow()
            if not session.last_active_at or (now - session.last_active_at).total_seconds() > 60:
                session.last_active_at = now
                db.commit()
            # Stash session_id on the user object for downstream use
            user._current_session_id = session_id
        else:
            user._current_session_id = None
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


# ============================================================================
# Pydantic Schemas
# ============================================================================

class ProfileResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: str
    updated_at: str
    last_login_at: Optional[str] = None
    password_changed_at: Optional[str] = None
    mfa_enabled: bool
    mfa_setup_complete: bool
    api_key_count: int
    active_api_key_count: int
    avatar: Optional[str] = None
    allowed_countries: Optional[str] = None
    new_login_alert_enabled: bool = True
    password_change_alert_enabled: bool = True
    mfa_change_alert_enabled: bool = True
    failed_login_alert_enabled: bool = True
    weekly_security_digest_enabled: bool = False

class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    allowed_countries: Optional[str] = None
    current_password: Optional[str] = None

class ProfileUpdateResponse(BaseModel):
    message: str
    email: str
    full_name: str
    allowed_countries: Optional[str] = None


class NotificationPreferencesResponse(BaseModel):
    new_login_alert_enabled: bool
    password_change_alert_enabled: bool
    mfa_change_alert_enabled: bool
    failed_login_alert_enabled: bool
    weekly_security_digest_enabled: bool


class NotificationPreferencesUpdateRequest(BaseModel):
    new_login_alert_enabled: Optional[bool] = None
    password_change_alert_enabled: Optional[bool] = None
    mfa_change_alert_enabled: Optional[bool] = None
    failed_login_alert_enabled: Optional[bool] = None
    weekly_security_digest_enabled: Optional[bool] = None

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class ChangePasswordResponse(BaseModel):
    message: str

class DeleteAccountRequest(BaseModel):
    password: str
    confirmation: str  # Must be "DELETE MY ACCOUNT"


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/profile", response_model=ProfileResponse)
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get the current user's profile information."""
    total_keys = db.query(APIKey).filter(APIKey.user_id == user.id).count()
    active_keys = db.query(APIKey).filter(
        APIKey.user_id == user.id,
        APIKey.is_active == True
    ).count()

    return ProfileResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else "",
        updated_at=user.updated_at.isoformat() if user.updated_at else "",
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        password_changed_at=user.password_changed_at.isoformat() if user.password_changed_at else None,
        mfa_enabled=user.mfa_enabled,
        mfa_setup_complete=user.mfa_setup_complete,
        api_key_count=total_keys,
        active_api_key_count=active_keys,
        avatar=user.avatar,
        allowed_countries=user.allowed_countries,
        new_login_alert_enabled=user.new_login_alert_enabled,
        password_change_alert_enabled=user.password_change_alert_enabled,
        mfa_change_alert_enabled=user.mfa_change_alert_enabled,
        failed_login_alert_enabled=user.failed_login_alert_enabled,
        weekly_security_digest_enabled=user.weekly_security_digest_enabled,
    )


@router.patch("/profile", response_model=ProfileUpdateResponse)
def update_profile(
    data: ProfileUpdateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user's profile (name and/or email)."""
    profile_changes = []
    geo_policy_changed = False
    normalized_policy = user.allowed_countries
    requires_reauth = False

    if data.full_name is not None:
        name = data.full_name.strip()
        if len(name) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Full name must be at least 2 characters"
            )
        if len(name) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Full name must be less than 100 characters"
            )
        if name != user.full_name:
            user.full_name = name
            profile_changes.append("full_name")

    if data.email is not None:
        new_email = data.email.lower().strip()
        if new_email != user.email:
            requires_reauth = True
            # Check for duplicate
            existing = db.query(User).filter(User.email == new_email).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already in use"
                )
            user.email = new_email
            profile_changes.append("email")

    if data.allowed_countries is not None:
        normalized_policy = normalize_allowed_countries(data.allowed_countries)
        if normalized_policy != user.allowed_countries:
            requires_reauth = True
            user.allowed_countries = normalized_policy
            geo_policy_changed = True

    if requires_reauth:
        current_password = (data.current_password or "").strip()
        if not current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is required for sensitive profile changes"
            )
        if not pwd_context.verify(current_password, user.password_hash):
            log_audit(
                db,
                user.id,
                "reauth_failed",
                "Failed password re-authentication for sensitive profile change",
                request,
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )

    user.updated_at = datetime.now(timezone.utc)
    if profile_changes:
        log_audit(
            db,
            user.id,
            "profile_updated",
            "Profile fields updated: " + ", ".join(profile_changes),
            request,
        )
    if geo_policy_changed:
        policy_detail = normalized_policy or "Global access allowed"
        log_audit(
            db,
            user.id,
            "ztna_policy_updated",
            f"Zero Trust geo policy updated: {policy_detail}",
            request,
        )
    db.commit()
    db.refresh(user)

    return ProfileUpdateResponse(
        message="Profile updated successfully",
        email=user.email,
        full_name=user.full_name,
        allowed_countries=user.allowed_countries,
    )


@router.get("/notification-preferences", response_model=NotificationPreferencesResponse)
def get_notification_preferences(user: User = Depends(get_current_user)):
    """Return persisted notification preferences for the authenticated user."""
    return NotificationPreferencesResponse(
        new_login_alert_enabled=user.new_login_alert_enabled,
        password_change_alert_enabled=user.password_change_alert_enabled,
        mfa_change_alert_enabled=user.mfa_change_alert_enabled,
        failed_login_alert_enabled=user.failed_login_alert_enabled,
        weekly_security_digest_enabled=user.weekly_security_digest_enabled,
    )


@router.patch("/notification-preferences", response_model=NotificationPreferencesResponse)
def update_notification_preferences(
    data: NotificationPreferencesUpdateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update persisted notification preferences for the authenticated user."""
    changed = False

    if data.new_login_alert_enabled is not None and data.new_login_alert_enabled != user.new_login_alert_enabled:
        user.new_login_alert_enabled = data.new_login_alert_enabled
        user.updated_at = datetime.now(timezone.utc)
        changed = True
    if data.password_change_alert_enabled is not None and data.password_change_alert_enabled != user.password_change_alert_enabled:
        user.password_change_alert_enabled = data.password_change_alert_enabled
        user.updated_at = datetime.now(timezone.utc)
        changed = True
    if data.mfa_change_alert_enabled is not None and data.mfa_change_alert_enabled != user.mfa_change_alert_enabled:
        user.mfa_change_alert_enabled = data.mfa_change_alert_enabled
        user.updated_at = datetime.now(timezone.utc)
        changed = True
    if data.failed_login_alert_enabled is not None and data.failed_login_alert_enabled != user.failed_login_alert_enabled:
        user.failed_login_alert_enabled = data.failed_login_alert_enabled
        user.updated_at = datetime.now(timezone.utc)
        changed = True
    if data.weekly_security_digest_enabled is not None and data.weekly_security_digest_enabled != user.weekly_security_digest_enabled:
        user.weekly_security_digest_enabled = data.weekly_security_digest_enabled
        user.updated_at = datetime.now(timezone.utc)
        changed = True

    if changed:
        states = []
        states.append(f"New login alert email {'enabled' if user.new_login_alert_enabled else 'disabled'}")
        states.append(f"Password change alert email {'enabled' if user.password_change_alert_enabled else 'disabled'}")
        states.append(f"MFA change alert email {'enabled' if user.mfa_change_alert_enabled else 'disabled'}")
        states.append(f"Failed login alert email {'enabled' if user.failed_login_alert_enabled else 'disabled'}")
        states.append(f"Weekly security digest {'enabled' if user.weekly_security_digest_enabled else 'disabled'}")
        log_audit(
            db,
            user.id,
            "notification_preferences_updated",
            "; ".join(states),
            request,
        )
        db.commit()

    return NotificationPreferencesResponse(
        new_login_alert_enabled=user.new_login_alert_enabled,
        password_change_alert_enabled=user.password_change_alert_enabled,
        mfa_change_alert_enabled=user.mfa_change_alert_enabled,
        failed_login_alert_enabled=user.failed_login_alert_enabled,
        weekly_security_digest_enabled=user.weekly_security_digest_enabled,
    )


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    data: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change current user's password. Requires current password."""
    # Verify current password
    if not pwd_context.verify(data.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Validate new password strength
    new_pw = data.new_password
    if len(new_pw) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters"
        )
    if not re.search(r"[A-Z]", new_pw):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must contain at least one uppercase letter"
        )
    if not re.search(r"[a-z]", new_pw):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must contain at least one lowercase letter"
        )
    if not re.search(r"\d", new_pw):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must contain at least one digit"
        )

    # Hash and save
    user.password_hash = pwd_context.hash(new_pw)
    user.password_changed_at = datetime.now(timezone.utc)
    # Bump token_version to invalidate all other sessions
    user.token_version = (user.token_version or 0) + 1
    user.updated_at = datetime.now(timezone.utc)

    # Revoke all session rows except the current one
    current_sid = getattr(user, '_current_session_id', None)
    all_sessions = db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.is_revoked == False
    ).all()
    for s in all_sessions:
        if s.session_token != current_sid:
            s.is_revoked = True

    log_audit(db, user.id, "password_changed", "Password updated, other sessions revoked", request)
    db.commit()

    if user.password_change_alert_enabled:
        client_ip = request.client.host if request.client else "Unknown"
        send_password_changed_notification(user.email, client_ip)

    return ChangePasswordResponse(message="Password changed successfully. You will be logged out of other sessions.")


@router.post("/delete-account")
def delete_account(
    data: DeleteAccountRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Permanently delete the current user's account."""
    # Verify password
    if not pwd_context.verify(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password is incorrect"
        )

    # Verify confirmation text
    if data.confirmation != "DELETE MY ACCOUNT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='You must type "DELETE MY ACCOUNT" to confirm'
        )

    # Delete user (cascade will remove API keys & password reset tokens)
    db.delete(user)
    db.commit()

    return {"message": "Account deleted successfully"}


# ============================================================================
# MFA — Authenticated Setup (for Profile page)
# ============================================================================

class MfaSetupCodeRequest(BaseModel):
    code: str


@router.post("/mfa/setup")
def user_mfa_setup(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Start MFA setup for an already-authenticated user.
    Returns QR code and secret for the authenticator app.
    """
    if user.mfa_enabled and user.mfa_setup_complete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled. Disable it first to re-setup."
        )

    # Generate new secret
    secret = generate_mfa_secret()
    user.mfa_secret = encrypt_secret(secret)
    db.commit()

    qr_code = generate_qr_code_base64(secret, user.email)

    return {
        "qr_code": qr_code,
        "secret": secret,
        "message": "Scan the QR code with your authenticator app, then verify with the 6-digit code."
    }


@router.post("/mfa/verify-setup")
def user_mfa_verify_setup(
    data: MfaSetupCodeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify the first TOTP code and complete MFA setup (authenticated user).
    Returns backup codes on success.
    """
    if user.mfa_enabled and user.mfa_setup_complete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already set up."
        )

    if not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA setup not started. Call /user/mfa/setup first."
        )

    secret_plain = decrypt_secret(user.mfa_secret)
    if not verify_totp(secret_plain, data.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code. Please try again with the current code from your authenticator."
        )

    # Generate backup codes
    plain_codes, hashed_codes = generate_backup_codes(8)
    user.mfa_backup_codes = json.dumps(hashed_codes)
    user.mfa_setup_complete = True
    user.mfa_enabled = True
    user.updated_at = datetime.now(timezone.utc)
    db.commit()

    if user.mfa_change_alert_enabled:
        client_ip = request.client.host if request.client else "Unknown"
        send_mfa_change_notification(user.email, True, client_ip)

    return {
        "success": True,
        "backup_codes": plain_codes,
        "message": "MFA setup complete! Save your backup codes securely."
    }


# ============================================================================
# Avatar Upload
# ============================================================================

import base64

AVATAR_MAX_BYTES = 2 * 1024 * 1024  # 2 MB after Base64 decode
AVATAR_ALLOWED_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


class AvatarUploadRequest(BaseModel):
    avatar: str  # Data URL: data:image/<type>;base64,<data>


@router.post("/avatar")
def upload_avatar(
    data: AvatarUploadRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload or replace the user's profile avatar (Base64 Data URL)."""
    raw = data.avatar.strip()

    # Validate Data URL format
    if not raw.startswith("data:image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Must be a data:image/... Data URL.",
        )

    try:
        header, b64_data = raw.split(";base64,", 1)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Data URL — missing ;base64, separator.",
        )

    # Validate MIME type
    mime = header.replace("data:", "")  # e.g. "image/png"
    if mime not in AVATAR_ALLOWED_MIMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image type '{mime}'. Allowed: PNG, JPEG, GIF, WebP.",
        )

    # Validate size (decode to check real byte count)
    try:
        decoded = base64.b64decode(b64_data)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Base64 data.",
        )

    if len(decoded) > AVATAR_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image too large. Maximum size is {AVATAR_MAX_BYTES // (1024*1024)} MB.",
        )

    # Validate it looks like real image data (magic bytes)
    MAGIC = {
        "image/png": b"\x89PNG",
        "image/jpeg": b"\xff\xd8\xff",
        "image/gif": b"GIF8",
        "image/webp": b"RIFF",
    }
    expected_magic = MAGIC.get(mime)
    if expected_magic and decoded[:len(expected_magic)] != expected_magic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match the claimed image type.",
        )

    user.avatar = raw
    user.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "Avatar updated successfully"}


@router.delete("/avatar")
def remove_avatar(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove the user's profile avatar."""
    if not user.avatar:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No avatar to remove.",
        )

    user.avatar = None
    user.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "Avatar removed"}


# ============================================================================
# Active Sessions Management
# ============================================================================

from typing import List

class SessionResponse(BaseModel):
    id: int
    device_label: str
    ip_address: str
    country: Optional[str] = None
    city: Optional[str] = None
    is_new_location: bool = False
    created_at: str
    last_active_at: str
    is_current: bool


@router.get("/sessions", response_model=List[SessionResponse])
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List all active (non-revoked) sessions for the current user."""
    sessions = db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.is_revoked == False
    ).order_by(UserSession.last_active_at.desc()).all()

    current_sid = getattr(user, '_current_session_id', None)

    return [
        SessionResponse(
            id=s.id,
            device_label=s.device_label or "Unknown Device",
            ip_address=s.ip_address or "—",
            country=s.country,
            city=s.city,
            is_new_location=s.is_new_location or False,
            created_at=(s.created_at.isoformat() + "Z") if s.created_at else "",
            last_active_at=(s.last_active_at.isoformat() + "Z") if s.last_active_at else "",
            is_current=(s.session_token == current_sid) if current_sid else False,
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revoke a single session by its database ID."""
    session = db.query(UserSession).filter(
        UserSession.id == session_id,
        UserSession.user_id == user.id
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    current_sid = getattr(user, '_current_session_id', None)
    if session.session_token == current_sid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke your current session. Use logout instead."
        )

    session.is_revoked = True
    log_audit(db, user.id, "session_revoked", f"Session {session_id} revoked", request)
    db.commit()

    return {"message": "Session revoked successfully"}


@router.delete("/sessions")
def revoke_all_other_sessions(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revoke all sessions except the current one."""
    current_sid = getattr(user, '_current_session_id', None)

    sessions = db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.is_revoked == False
    ).all()

    revoked_count = 0
    for s in sessions:
        if s.session_token != current_sid:
            s.is_revoked = True
            revoked_count += 1

    log_audit(db, user.id, "sessions_revoked_all", f"{revoked_count} sessions revoked", request)
    db.commit()

    return {"message": f"{revoked_count} session(s) revoked", "revoked_count": revoked_count}


# ============================================================================
# Audit Log
# ============================================================================

@router.get("/audit-log")
def get_audit_log(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return the current user's security audit log (newest first)."""
    from models import AuditLog

    events = (
        db.query(AuditLog)
        .filter(AuditLog.user_id == user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )

    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "detail": e.detail,
            "ip_address": e.ip_address,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]

@router.get("/audit-log/export")
def export_audit_log(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export the last 90 days of audit logs as a CSV file."""
    from models import AuditLog
    import csv
    import io
    from datetime import datetime, timedelta
    from fastapi.responses import Response

    cutoff = datetime.utcnow() - timedelta(days=90)
    events = (
        db.query(AuditLog)
        .filter(AuditLog.user_id == user.id)
        .filter(AuditLog.created_at >= cutoff)
        .order_by(AuditLog.created_at.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp (UTC)", "Event Type", "Detail", "IP Address", "User Agent"])

    for e in events:
        writer.writerow([
            e.created_at.isoformat() if e.created_at else "",
            e.event_type,
            "\"" + str(e.detail) + "\"" if e.detail else "",
            e.ip_address or "",
            e.user_agent or ""
        ])

    headers = {
        "Content-Disposition": f"attachment; filename=audit_logs_{user.id}_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    }
    return Response(content=output.getvalue(), media_type="text/csv", headers=headers)
