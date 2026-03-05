"""
User Self-Service Routes
========================
Endpoints for the user panel — users manage their own profile, password, etc.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header
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

class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None

class ProfileUpdateResponse(BaseModel):
    message: str
    email: str
    full_name: str

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
    )


@router.patch("/profile", response_model=ProfileUpdateResponse)
def update_profile(
    data: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user's profile (name and/or email)."""
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
        user.full_name = name

    if data.email is not None:
        new_email = data.email.lower().strip()
        if new_email != user.email:
            # Check for duplicate
            existing = db.query(User).filter(User.email == new_email).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already in use"
                )
            user.email = new_email

    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    return ProfileUpdateResponse(
        message="Profile updated successfully",
        email=user.email,
        full_name=user.full_name,
    )


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    data: ChangePasswordRequest,
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

    db.commit()

    return ChangePasswordResponse(message="Password changed successfully. You will be logged out of other sessions.")


@router.post("/delete-account")
def delete_account(
    data: DeleteAccountRequest,
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
            created_at=(s.created_at.isoformat() + "Z") if s.created_at else "",
            last_active_at=(s.last_active_at.isoformat() + "Z") if s.last_active_at else "",
            is_current=(s.session_token == current_sid) if current_sid else False,
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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
    db.commit()

    return {"message": "Session revoked successfully"}


@router.delete("/sessions")
def revoke_all_other_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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

    db.commit()

    return {"message": f"{revoked_count} session(s) revoked", "revoked_count": revoked_count}
