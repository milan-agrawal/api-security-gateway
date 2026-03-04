"""
MFA (Multi-Factor Authentication) endpoints
Handles TOTP-based 2FA for users and MFA for admins
"""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional
import jwt
import os
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deps import get_db
from models import User
from utils import (
    generate_mfa_secret,
    generate_qr_code_base64,
    verify_totp,
    generate_backup_codes,
    verify_backup_code,
    get_totp_uri
)
from utils import encrypt_secret, decrypt_secret

router = APIRouter(prefix="/auth/mfa", tags=["MFA"])

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY environment variable is not set")
ALGORITHM = "HS256"

# Temp token for MFA verification (short-lived)
MFA_TEMP_TOKEN_EXPIRE_MINUTES = 5


# ============================================================================
# Request/Response Models
# ============================================================================

class MFASetupResponse(BaseModel):
    """Response for MFA setup - contains QR code and secret"""
    qr_code: str  # Base64 encoded QR code image (for frontend: use in <img src="...">)
    secret: str  # For manual entry in authenticator
    message: str


class MFASetupRequest(BaseModel):
    """Request for MFA setup with temp token"""
    temp_token: str


class MFAVerifySetupRequest(BaseModel):
    """Request to verify first TOTP code and complete setup"""
    temp_token: str
    otp_code: str  # 6-digit TOTP code


class MFAVerifySetupResponse(BaseModel):
    """Response after completing MFA setup - includes full auth token and backup codes"""
    token: str
    email: str
    role: str
    full_name: str
    backup_codes: list[str]
    message: str


class MFAVerifyRequest(BaseModel):
    """Request to verify TOTP during login"""
    temp_token: str
    otp_code: str  # 6-digit TOTP code or backup code
    is_backup_code: bool = False


class MFAVerifyResponse(BaseModel):
    """Response after successful MFA verification"""
    token: str
    email: str
    role: str
    full_name: str


class MFAStatusResponse(BaseModel):
    """Response for MFA status check"""
    mfa_enabled: bool
    mfa_setup_complete: bool
    backup_codes_remaining: int


# ============================================================================
# Helper Functions
# ============================================================================

def get_current_user_from_token(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """Extract and verify user from JWT token"""
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


def create_mfa_temp_token(email: str, user_id: int) -> str:
    """Create a short-lived token for MFA verification step"""
    expire = datetime.utcnow() + timedelta(minutes=MFA_TEMP_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": email,
        "user_id": user_id,
        "type": "mfa_temp",
        "exp": expire
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_mfa_temp_token(temp_token: str) -> dict:
    """Verify the MFA temp token and return payload"""
    try:
        payload = jwt.decode(temp_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "mfa_temp":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA session expired. Please login again."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MFA token"
        )


# Rate limiting for MFA verification attempts
# Stores: {user_id: [timestamp1, timestamp2, ...]}
_mfa_verify_attempts: dict[int, list[datetime]] = {}
MAX_MFA_ATTEMPTS = 5          # max failed attempts
MFA_LOCKOUT_MINUTES = 15      # lockout window


def _check_mfa_rate_limit(user_id: int):
    """Raise 429 if too many MFA attempts within the lockout window."""
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=MFA_LOCKOUT_MINUTES)
    attempts = _mfa_verify_attempts.get(user_id, [])
    # Prune old entries
    attempts = [t for t in attempts if t > cutoff]
    _mfa_verify_attempts[user_id] = attempts
    if len(attempts) >= MAX_MFA_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many verification attempts. Please wait {MFA_LOCKOUT_MINUTES} minutes."
        )


def _record_mfa_attempt(user_id: int):
    """Record a failed MFA attempt."""
    _mfa_verify_attempts.setdefault(user_id, []).append(datetime.utcnow())


def _clear_mfa_attempts(user_id: int):
    """Clear attempts on successful verification."""
    _mfa_verify_attempts.pop(user_id, None)


def create_full_access_token(email: str, role: str, full_name: str, user_id: int = None) -> str:
    """Create the actual access token after successful MFA"""
    expire = datetime.utcnow() + timedelta(hours=24)
    payload = {
        "sub": email,
        "role": role,
        "full_name": full_name,
        "exp": expire
    }
    if user_id is not None:
        payload["user_id"] = user_id
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ============================================================================
# MFA Endpoints
# ============================================================================

@router.post("/setup", response_model=MFASetupResponse)
def setup_mfa(
    request: MFASetupRequest,
    db: Session = Depends(get_db)
):
    """
    Initialize MFA setup - generates QR code.
    Called when user needs to set up their authenticator app.
    Uses temp_token from login flow (before MFA is complete).
    """
    # Verify temp token and get user
    payload = verify_mfa_temp_token(request.temp_token)
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Generate new secret if not exists or setup not complete
    if not user.mfa_secret or not user.mfa_setup_complete:
        secret = generate_mfa_secret()
        # store encrypted at rest if configured
        user.mfa_secret = encrypt_secret(secret)
        db.commit()
    else:
        # decrypt for use (if stored encrypted)
        secret = decrypt_secret(user.mfa_secret)
    
    # Generate QR code
    qr_code = generate_qr_code_base64(secret, user.email)
    
    return MFASetupResponse(
        qr_code=qr_code,
        secret=secret,
        message="Scan the QR code with your authenticator app, then enter the 6-digit code to complete setup."
    )


@router.post("/verify-setup", response_model=MFAVerifySetupResponse)
def verify_mfa_setup(
    request: MFAVerifySetupRequest,
    db: Session = Depends(get_db)
):
    """
    Complete MFA setup by verifying the first TOTP code.
    This confirms the user has correctly set up their authenticator.
    Returns full auth token and backup codes.
    """
    # Verify temp token and get user
    payload = verify_mfa_temp_token(request.temp_token)
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    if not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA setup not initialized. Call /setup first."
        )
    
    if user.mfa_setup_complete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already set up for this account."
        )
    
    # Rate-limit setup verification
    _check_mfa_rate_limit(user.id)
    
    # Verify the TOTP code (decrypt secret first if needed)
    secret_plain = decrypt_secret(user.mfa_secret)
    if not verify_totp(secret_plain, request.otp_code):
        _record_mfa_attempt(user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code. Please try again with the current code from your authenticator."
        )
    
    _clear_mfa_attempts(user.id)
    
    # Generate backup codes
    plain_codes, hashed_codes = generate_backup_codes(8)
    user.mfa_backup_codes = json.dumps(hashed_codes)
    
    # Mark setup as complete
    user.mfa_setup_complete = True
    user.mfa_enabled = True
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    
    # Generate full access token
    token = create_full_access_token(user.email, user.role, user.full_name, user.id)
    
    return MFAVerifySetupResponse(
        token=token,
        email=user.email,
        role=user.role,
        full_name=user.full_name,
        backup_codes=plain_codes,
        message="MFA setup complete! Save your backup codes securely."
    )


@router.post("/verify", response_model=MFAVerifyResponse)
def verify_mfa(
    request: MFAVerifyRequest,
    db: Session = Depends(get_db)
):
    """
    Verify TOTP code during login process.
    Called after password verification if MFA is enabled.
    """
    # Verify temp token
    payload = verify_mfa_temp_token(request.temp_token)
    
    # Get user
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled for this account"
        )
    
    # Rate-limit verification attempts
    _check_mfa_rate_limit(user.id)
    
    is_valid = False
    
    if request.is_backup_code:
        # Verify backup code
        is_valid, updated_codes = verify_backup_code(request.otp_code, user.mfa_backup_codes or "[]")
        if is_valid:
            user.mfa_backup_codes = updated_codes
            db.commit()
    else:
        # Verify TOTP code (decrypt secret first if needed)
        secret_plain = decrypt_secret(user.mfa_secret)
        is_valid = verify_totp(secret_plain, request.otp_code)
    
    if not is_valid:
        _record_mfa_attempt(user.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification code"
        )
    
    _clear_mfa_attempts(user.id)
    
    # Generate full access token
    token = create_full_access_token(user.email, user.role, user.full_name, user.id)
    
    return MFAVerifyResponse(
        token=token,
        email=user.email,
        role=user.role,
        full_name=user.full_name
    )


@router.get("/status", response_model=MFAStatusResponse)
def get_mfa_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_from_token)
):
    """Get current MFA status for the authenticated user"""
    backup_codes_remaining = 0
    if user.mfa_backup_codes:
        try:
            codes = json.loads(user.mfa_backup_codes)
            backup_codes_remaining = len(codes)
        except json.JSONDecodeError:
            pass
    
    return MFAStatusResponse(
        mfa_enabled=user.mfa_enabled,
        mfa_setup_complete=user.mfa_setup_complete,
        backup_codes_remaining=backup_codes_remaining
    )


@router.post("/regenerate-backup-codes")
def regenerate_backup_codes(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_from_token)
):
    """
    Regenerate backup codes (invalidates old ones).
    User must have MFA set up already.
    """
    if not user.mfa_enabled or not user.mfa_setup_complete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA must be set up before regenerating backup codes"
        )
    
    # Generate new backup codes
    plain_codes, hashed_codes = generate_backup_codes(8)
    user.mfa_backup_codes = json.dumps(hashed_codes)
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    
    return {
        "success": True,
        "backup_codes": plain_codes,
        "message": "New backup codes generated. Old codes are now invalid. Save these codes securely!"
    }


@router.post("/disable")
def disable_mfa(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_from_token)
):
    """
    Disable MFA for a user account.
    Note: Admins cannot disable their own MFA (it's mandatory).
    """
    if user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot disable MFA. Multi-factor authentication is mandatory for admin accounts."
        )
    
    if not user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled for this account"
        )
    
    # Disable MFA
    user.mfa_enabled = False
    user.mfa_setup_complete = False
    user.mfa_secret = None
    user.mfa_backup_codes = None
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    
    return {
        "success": True,
        "message": "Two-factor authentication has been disabled for your account."
    }
