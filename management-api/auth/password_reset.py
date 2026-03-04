from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr, validator
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from passlib.context import CryptContext
import secrets
import hashlib
import hmac
import os
import re

from deps import get_db
from models import User, PasswordResetToken
from utils import send_password_reset_email, send_password_changed_notification

router = APIRouter(prefix="/auth", tags=["PasswordReset"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Token TTL (minutes)
RESET_TOKEN_EXPIRE_MINUTES = int(os.getenv('RESET_TOKEN_EXPIRE_MINUTES', '60'))


# ============================================================================
# Rate-limiting (in-memory; use Redis in production)
# ============================================================================
# Per-IP:    max 5 forgot requests per 15 minutes
# Per-email: max 3 forgot requests per 15 minutes
_forgot_ip_attempts: dict[str, list[datetime]] = {}
_forgot_email_attempts: dict[str, list[datetime]] = {}
FORGOT_MAX_PER_IP = 5
FORGOT_MAX_PER_EMAIL = 3
FORGOT_WINDOW_MINUTES = 15

# Rate-limiting for reset-password endpoint (brute-force protection)
_reset_attempts: dict[str, list[datetime]] = {}
RESET_MAX_ATTEMPTS = 5
RESET_WINDOW_MINUTES = 15


def _prune(entries: list[datetime], cutoff: datetime) -> list[datetime]:
    """Remove entries older than cutoff."""
    return [t for t in entries if t > cutoff]


def _check_forgot_rate_limit(ip: str, email: str):
    """Raise 429 if the caller exceeds either rate-limit bucket."""
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=FORGOT_WINDOW_MINUTES)

    # --- per-IP ---
    ip_attempts = _prune(_forgot_ip_attempts.get(ip, []), cutoff)
    _forgot_ip_attempts[ip] = ip_attempts
    if len(ip_attempts) >= FORGOT_MAX_PER_IP:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many requests. Please wait {FORGOT_WINDOW_MINUTES} minutes before trying again."
        )

    # --- per-email ---
    email_lower = email.lower()
    email_attempts = _prune(_forgot_email_attempts.get(email_lower, []), cutoff)
    _forgot_email_attempts[email_lower] = email_attempts
    if len(email_attempts) >= FORGOT_MAX_PER_EMAIL:
        # Do NOT tell the caller the email exists — return silently later
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many requests. Please wait {FORGOT_WINDOW_MINUTES} minutes before trying again."
        )


def _record_forgot_attempt(ip: str, email: str):
    """Record a successful forgot-password request for rate-limiting."""
    now = datetime.utcnow()
    _forgot_ip_attempts.setdefault(ip, []).append(now)
    _forgot_email_attempts.setdefault(email.lower(), []).append(now)


def _check_reset_rate_limit(ip: str):
    """Raise 429 if too many reset attempts from this IP."""
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=RESET_WINDOW_MINUTES)
    attempts = _prune(_reset_attempts.get(ip, []), cutoff)
    _reset_attempts[ip] = attempts
    if len(attempts) >= RESET_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts. Please wait {RESET_WINDOW_MINUTES} minutes."
        )


def _record_reset_attempt(ip: str):
    """Record a reset attempt for rate-limiting."""
    _reset_attempts.setdefault(ip, []).append(datetime.utcnow())


# ============================================================================
# Password strength validation
# ============================================================================
MIN_PASSWORD_LENGTH = 8


def _validate_password_strength(password: str):
    """Raise 400 if the password does not meet minimum complexity."""
    errors = []
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"at least {MIN_PASSWORD_LENGTH} characters")
    if not re.search(r'[A-Z]', password):
        errors.append("an uppercase letter")
    if not re.search(r'[a-z]', password):
        errors.append("a lowercase letter")
    if not re.search(r'\d', password):
        errors.append("a digit")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("a special character")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must contain {', '.join(errors)}."
        )


# ============================================================================
# Request / Response models
# ============================================================================

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ============================================================================
# Endpoints
# ============================================================================

@router.post('/forgot-password')
def forgot_password(request: ForgotPasswordRequest, http_request: Request, db: Session = Depends(get_db)):
    """Create a one-time reset token and email it to the user. Always return generic success (no enumeration)."""
    # Generic response — same regardless of email existence
    resp = {"success": True, "message": "If the email exists, you will receive password reset instructions."}

    client_ip = http_request.client.host if http_request.client else "unknown"

    # Rate-limit check (may raise 429)
    _check_forgot_rate_limit(client_ip, request.email)

    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        # Record attempt against IP even for non-existent emails to prevent enumeration probing
        _record_forgot_attempt(client_ip, request.email)
        return resp

    # Don't send reset links to deactivated accounts (but return same response to prevent enumeration)
    if not user.is_active:
        _record_forgot_attempt(client_ip, request.email)
        return resp

    # Invalidate any outstanding (unused, unexpired) tokens for this user
    now = datetime.utcnow()
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False,
        PasswordResetToken.expires_at > now
    ).update({"used": True})

    # Generate token (raw) and store only hash
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    expires_at = now + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)

    prt = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        created_at=now,
        expires_at=expires_at,
        used=False,
        request_ip=client_ip,
        request_user_agent=http_request.headers.get('user-agent')
    )

    db.add(prt)
    db.commit()

    # Record rate-limit hit
    _record_forgot_attempt(client_ip, request.email)

    # Send email (best-effort)
    try:
        send_password_reset_email(user.email, raw_token, expires_minutes=RESET_TOKEN_EXPIRE_MINUTES)
    except Exception:
        # swallow email errors — do not expose to caller
        pass

    return resp


@router.post('/reset-password')
def reset_password(body: ResetPasswordRequest, http_request: Request, db: Session = Depends(get_db)):
    """Verify token and update user's password. Token is single-use and time-limited."""
    client_ip = http_request.client.host if http_request.client else "unknown"
    
    # Rate-limit to prevent brute-force token guessing
    _check_reset_rate_limit(client_ip)
    
    # Validate password strength before doing any DB work
    _validate_password_strength(body.new_password)

    # Compute hash of submitted token
    submitted_hash = hashlib.sha256(body.token.encode()).hexdigest()
    now = datetime.utcnow()

    # Find all unexpired, unused tokens and do constant-time comparison
    # This prevents timing attacks that could leak token existence
    prt = None
    candidates = db.query(PasswordResetToken).filter(
        PasswordResetToken.used == False,
        PasswordResetToken.expires_at > now
    ).all()
    
    for candidate in candidates:
        if hmac.compare_digest(candidate.token_hash, submitted_hash):
            prt = candidate
            break
    
    # Record attempt for rate-limiting (after lookup, to prevent timing leak)
    _record_reset_attempt(client_ip)

    if not prt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == prt.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")
    
    # Block reset for deactivated accounts
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    # Update password
    user.password_hash = pwd_context.hash(body.new_password)
    user.updated_at = datetime.utcnow()

    # Invalidate existing sessions by bumping token_version
    user.token_version = (user.token_version or 0) + 1

    # Mark ALL remaining tokens for this user as used (belt-and-suspenders)
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False
    ).update({"used": True})

    db.add(user)
    db.commit()

    # Send notification email (best-effort) so user knows their password was changed
    try:
        send_password_changed_notification(user.email, client_ip)
    except Exception:
        pass  # don't fail the request if email fails

    return {"success": True, "message": "Password has been reset successfully"}
