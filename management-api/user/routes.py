"""
User Self-Service Routes
========================
Endpoints for the user panel — users manage their own profile, password, etc.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header, Request, Query, UploadFile, File, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, validator
from passlib.context import CryptContext
from typing import Optional
from datetime import datetime, timezone, timedelta
import jwt
import os
import re
import json
import html
import secrets
import hashlib
import hmac
import mimetypes
from urllib.parse import quote
from urllib import request as urllib_request

from deps import get_db
from models import User, APIKey, UserSession, EmailChangeToken, SupportTicket, SupportTicketMessage, SupportTicketAttachment
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
    send_email_change_verification_email,
    send_email_change_notice,
    send_support_ticket_notification,
)
from support_storage import (
    support_attachment_read_bytes,
    support_attachment_safe_filename,
    support_attachment_write_bytes,
)
from rate_limit import is_rate_limited

router = APIRouter(prefix="/user", tags=["User Self-Service"])

# Password hashing (same config as main.py)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
EMAIL_CHANGE_TOKEN_EXPIRE_MINUTES = int(os.getenv("EMAIL_CHANGE_TOKEN_EXPIRE_MINUTES", "60"))
MAX_SUPPORT_ATTACHMENT_BYTES = int(os.getenv("SUPPORT_ATTACHMENT_MAX_BYTES", str(2 * 1024 * 1024)))
ALLOWED_SUPPORT_ATTACHMENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/json",
}
ALLOWED_SUPPORT_ATTACHMENT_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "txt", "csv", "json", "log"}
PRIVACY_TRANSLATE_RATE_LIMIT = int(os.getenv("PRIVACY_TRANSLATE_RATE_LIMIT", "40"))
PRIVACY_TRANSLATE_WINDOW_SECONDS = int(os.getenv("PRIVACY_TRANSLATE_WINDOW_SECONDS", "60"))
PRIVACY_TRANSLATION_CACHE: dict[str, str] = {}


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
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is no longer valid for this account"
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
    pending_email: Optional[str] = None
    pending_email_expires_at: Optional[str] = None
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
    pending_email: Optional[str] = None
    pending_email_expires_at: Optional[str] = None


class PendingEmailResponse(BaseModel):
    message: str
    pending_email: Optional[str] = None
    pending_email_expires_at: Optional[str] = None


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


class PrivacyTranslateRequest(BaseModel):
    target_locale: str
    texts: list[str]

    @validator("target_locale")
    def validate_target_locale(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", normalized):
            raise ValueError("Invalid locale format")
        return normalized

    @validator("texts")
    def validate_texts(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("texts cannot be empty")
        if len(value) > 250:
            raise ValueError("Too many text fragments")
        total = 0
        for item in value:
            if not isinstance(item, str):
                raise ValueError("All texts must be strings")
            if len(item) > 2000:
                raise ValueError("A text fragment is too large")
            total += len(item)
        if total > 60000:
            raise ValueError("Total translation payload is too large")
        return value


class PrivacyTranslateResponse(BaseModel):
    target_locale: str
    texts: list[str]
    provider_available: bool
    provider_message: Optional[str] = None


class VerifyEmailChangeRequest(BaseModel):
    token: str


class SupportTicketCreateRequest(BaseModel):
    category: str
    priority: str
    subject: str
    description: str
    contact_email: EmailStr
    related_route: Optional[str] = None

    @validator("category")
    def validate_category(cls, v):
        allowed = {"api_issue", "account_issue", "security_issue", "bug_report", "general_question"}
        value = (v or "").strip().lower()
        if value not in allowed:
            raise ValueError("Invalid support ticket category")
        return value

    @validator("priority")
    def validate_priority(cls, v):
        allowed = {"low", "medium", "high", "critical"}
        value = (v or "").strip().lower()
        if value not in allowed:
            raise ValueError("Invalid support ticket priority")
        return value

    @validator("subject")
    def validate_subject(cls, v):
        value = (v or "").strip()
        if len(value) < 5:
            raise ValueError("Subject must be at least 5 characters")
        if len(value) > 120:
            raise ValueError("Subject must be 120 characters or fewer")
        return value

    @validator("description")
    def validate_description(cls, v):
        value = (v or "").strip()
        if len(value) < 20:
            raise ValueError("Description must be at least 20 characters")
        if len(value) > 5000:
            raise ValueError("Description must be 5000 characters or fewer")
        return value

    @validator("related_route")
    def validate_related_route(cls, v):
        if v is None:
            return None
        value = v.strip()
        return value[:80] if value else None


class SupportTicketListItem(BaseModel):
    id: int
    category: str
    priority: str
    subject: str
    description: str
    contact_email: str
    related_route: Optional[str] = None
    status: str
    created_at: str
    updated_at: str
    attachment_count: int = 0


class SupportTicketMessageItem(BaseModel):
    id: int
    author_type: str
    author_name: str
    author_email: str
    message: str
    created_at: str


class SupportTicketAttachmentItem(BaseModel):
    id: int
    filename: str
    content_type: str
    file_size: int
    uploader_type: str
    uploader_name: str
    uploader_email: str
    created_at: str
    download_url: str
    is_image: bool = False


class SupportTicketCreateResponse(BaseModel):
    success: bool
    message: str
    ticket: SupportTicketListItem


class SupportTicketListResponse(BaseModel):
    tickets: list[SupportTicketListItem]


class SupportTicketDetailResponse(BaseModel):
    ticket: SupportTicketListItem
    messages: list[SupportTicketMessageItem]
    attachments: list[SupportTicketAttachmentItem]


class SupportTicketMessageCreateRequest(BaseModel):
    message: str

    @validator("message")
    def validate_message(cls, v):
        value = (v or "").strip()
        if len(value) < 2:
            raise ValueError("Reply must be at least 2 characters")
        if len(value) > 4000:
            raise ValueError("Reply must be 4000 characters or fewer")
        return value


class SupportTicketReopenRequest(BaseModel):
    reason: str

    @validator("reason")
    def validate_reason(cls, v):
        value = (v or "").strip()
        if len(value) < 10:
            raise ValueError("Reopen reason must be at least 10 characters")
        if len(value) > 1200:
            raise ValueError("Reopen reason must be 1200 characters or fewer")
        return value


class SupportTicketMessageCreateResponse(BaseModel):
    success: bool
    message: str
    reply: SupportTicketMessageItem


class SupportTicketAttachmentCreateResponse(BaseModel):
    success: bool
    message: str
    attachment: SupportTicketAttachmentItem


class SupportWorkflowCounts(BaseModel):
    open: int
    in_review: int
    waiting_for_user: int
    escalated: int
    resolved: int
    closed: int


class SupportTicketOverviewResponse(BaseModel):
    total_tickets: int
    open_tickets: int
    critical_open_tickets: int
    security_tickets: int
    latest_ticket_updated_at: Optional[str] = None
    smtp_ready: bool
    workflow_counts: SupportWorkflowCounts


def _get_pending_email_change(db: Session, user_id: int) -> Optional[EmailChangeToken]:
    now = datetime.utcnow()
    return db.query(EmailChangeToken).filter(
        EmailChangeToken.user_id == user_id,
        EmailChangeToken.used == False,
        EmailChangeToken.expires_at > now
    ).order_by(EmailChangeToken.created_at.desc()).first()


def _support_normalize_status(value: Optional[str]) -> str:
    allowed = {"open", "in_review", "waiting_for_user", "escalated", "resolved", "closed", "reopen_requested"}
    normalized = (value or "open").strip().lower()
    return normalized if normalized in allowed else "open"


def _support_initial_status(category: str, priority: str) -> str:
    if (category or "").lower() == "security_issue":
        return "escalated"
    if (priority or "").lower() == "critical":
        return "escalated"
    return "open"


def _support_ticket_list_item(ticket: SupportTicket) -> SupportTicketListItem:
    return SupportTicketListItem(
        id=ticket.id,
        category=ticket.category,
        priority=ticket.priority,
        subject=ticket.subject,
        description=ticket.description,
        contact_email=ticket.contact_email,
        related_route=ticket.related_route,
        status=_support_normalize_status(ticket.status),
        created_at=ticket.created_at.isoformat() if ticket.created_at else "",
        updated_at=ticket.updated_at.isoformat() if ticket.updated_at else "",
        attachment_count=len(getattr(ticket, "attachments", []) or []),
    )


def _support_ticket_message_item(message: SupportTicketMessage) -> SupportTicketMessageItem:
    author = message.author
    author_type = (message.author_type or "user").lower()
    return SupportTicketMessageItem(
        id=message.id,
        author_type=author_type,
        author_name="User" if author_type == "user" else "Admin",
        author_email="",
        message=message.message,
        created_at=message.created_at.isoformat() if message.created_at else "",
    )


def _support_ticket_attachment_item(attachment: SupportTicketAttachment) -> SupportTicketAttachmentItem:
    content_type = attachment.content_type or "application/octet-stream"
    uploader_type = (attachment.uploader_type or "user").lower()
    return SupportTicketAttachmentItem(
        id=attachment.id,
        filename=attachment.filename,
        content_type=content_type,
        file_size=attachment.file_size,
        uploader_type=uploader_type,
        uploader_name="User" if uploader_type == "user" else "Admin",
        uploader_email="",
        created_at=attachment.created_at.isoformat() if attachment.created_at else "",
        download_url=f"/user/support-tickets/{attachment.ticket_id}/attachments/{attachment.id}/download",
        is_image=content_type.startswith("image/"),
    )


def _support_attachment_filename(filename: str) -> str:
    return support_attachment_safe_filename(filename)


def _support_attachment_extension(filename: str) -> str:
    ext = os.path.splitext((filename or "").lower().strip())[1].lstrip(".")
    return ext


def _support_sniff_content_type(filename: str, content: bytes, declared_content_type: str) -> str:
    ext = _support_attachment_extension(filename)
    declared = (declared_content_type or "").lower().strip()
    data = content or b""

    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"

    if ext == "json":
        try:
            json.loads(data.decode("utf-8"))
            return "application/json"
        except Exception:
            pass

    if ext in {"txt", "csv", "log", "json"}:
        try:
            data.decode("utf-8")
            if ext == "csv":
                return "text/csv"
            if ext == "json":
                return "application/json"
            return "text/plain"
        except Exception:
            pass

    guessed = (mimetypes.guess_type(filename)[0] or "").lower().strip()
    if guessed in ALLOWED_SUPPORT_ATTACHMENT_TYPES:
        return guessed
    if declared in ALLOWED_SUPPORT_ATTACHMENT_TYPES:
        return declared
    return "application/octet-stream"


def _support_validate_attachment_type(filename: str, content: bytes, declared_content_type: str) -> str:
    ext = _support_attachment_extension(filename)
    if ext not in ALLOWED_SUPPORT_ATTACHMENT_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported attachment file type"
        )

    detected = _support_sniff_content_type(filename, content, declared_content_type)
    if detected not in ALLOWED_SUPPORT_ATTACHMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported attachment file type"
        )
    return detected


def _support_enforce_rate_limit(actor_id: int, action: str, limit: int, window_seconds: int = 3600):
    blocked = is_rate_limited(
        namespace="support",
        actor_scope="user",
        actor_id=actor_id,
        action=action,
        limit=limit,
        window_seconds=window_seconds,
    )
    if blocked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many support actions. Please try again shortly."
        )


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
    pending_email_change = _get_pending_email_change(db, user.id)

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
        pending_email=pending_email_change.new_email if pending_email_change else None,
        pending_email_expires_at=pending_email_change.expires_at.isoformat() if pending_email_change and pending_email_change.expires_at else None,
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
    requested_email_change = None

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
            requested_email_change = new_email

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

    if requested_email_change:
        now = datetime.utcnow()
        db.query(EmailChangeToken).filter(
            EmailChangeToken.user_id == user.id,
            EmailChangeToken.used == False,
            EmailChangeToken.expires_at > now
        ).update({"used": True})

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        db.add(EmailChangeToken(
            user_id=user.id,
            new_email=requested_email_change,
            token_hash=token_hash,
            created_at=now,
            expires_at=now + timedelta(minutes=EMAIL_CHANGE_TOKEN_EXPIRE_MINUTES),
            used=False,
            request_ip=request.client.host if request.client else None,
            request_user_agent=request.headers.get("user-agent"),
        ))
        log_audit(
            db,
            user.id,
            "email_change_requested",
            f"Email change requested from {user.email} to {requested_email_change}",
            request,
        )
    db.commit()
    db.refresh(user)

    if requested_email_change:
        try:
            sent = send_email_change_verification_email(
                requested_email_change,
                user.full_name,
                raw_token,
                expires_minutes=EMAIL_CHANGE_TOKEN_EXPIRE_MINUTES,
            )
        except Exception:
            sent = False

        if not sent:
            db.query(EmailChangeToken).filter(
                EmailChangeToken.user_id == user.id,
                EmailChangeToken.used == False,
                EmailChangeToken.new_email == requested_email_change,
            ).update({"used": True})
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to send the verification email right now. Please try again."
            )

    pending_email_change = _get_pending_email_change(db, user.id)

    return ProfileUpdateResponse(
        message="Verification email sent to the new address. Your current email will stay active until verification is completed." if requested_email_change else "Profile updated successfully",
        email=user.email,
        full_name=user.full_name,
        allowed_countries=user.allowed_countries,
        pending_email=pending_email_change.new_email if pending_email_change else None,
        pending_email_expires_at=pending_email_change.expires_at.isoformat() if pending_email_change and pending_email_change.expires_at else None,
    )


@router.post("/email-change/resend", response_model=PendingEmailResponse)
def resend_pending_email_change(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    pending_email_change = _get_pending_email_change(db, user.id)
    if not pending_email_change:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending email change request found"
        )

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    now = datetime.utcnow()
    pending_email_change.token_hash = token_hash
    pending_email_change.created_at = now
    pending_email_change.expires_at = now + timedelta(minutes=EMAIL_CHANGE_TOKEN_EXPIRE_MINUTES)
    pending_email_change.request_ip = request.client.host if request.client else None
    pending_email_change.request_user_agent = request.headers.get("user-agent")
    user.updated_at = datetime.now(timezone.utc)
    db.commit()

    try:
        sent = send_email_change_verification_email(
            pending_email_change.new_email,
            user.full_name,
            raw_token,
            expires_minutes=EMAIL_CHANGE_TOKEN_EXPIRE_MINUTES,
        )
    except Exception:
        sent = False

    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to resend the verification email right now. Please try again."
        )

    log_audit(
        db,
        user.id,
        "email_change_verification_resent",
        f"Verification email resent for pending email change to {pending_email_change.new_email}",
        request,
    )
    db.commit()

    return PendingEmailResponse(
        message="Verification email resent to the pending new address.",
        pending_email=pending_email_change.new_email,
        pending_email_expires_at=pending_email_change.expires_at.isoformat() if pending_email_change.expires_at else None,
    )


@router.delete("/email-change", response_model=PendingEmailResponse)
def cancel_pending_email_change(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    pending_email_change = _get_pending_email_change(db, user.id)
    if not pending_email_change:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending email change request found"
        )

    cancelled_email = pending_email_change.new_email
    db.query(EmailChangeToken).filter(
        EmailChangeToken.user_id == user.id,
        EmailChangeToken.used == False
    ).update({"used": True})
    user.updated_at = datetime.now(timezone.utc)
    log_audit(
        db,
        user.id,
        "email_change_cancelled",
        f"Pending email change to {cancelled_email} was cancelled",
        request,
    )
    db.commit()

    return PendingEmailResponse(
        message="Pending email change cancelled. Your current email remains active.",
        pending_email=None,
        pending_email_expires_at=None,
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


@router.get("/support-tickets", response_model=SupportTicketListResponse)
def list_support_tickets(
    q: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(SupportTicket).filter(SupportTicket.user_id == user.id)
    if q:
        search = f"%{q.strip()}%"
        search_terms = [
            SupportTicket.subject.ilike(search),
            SupportTicket.description.ilike(search),
            SupportTicket.contact_email.ilike(search),
            SupportTicket.related_route.ilike(search),
            SupportTicket.category.ilike(search),
            SupportTicket.status.ilike(search),
        ]
        if q.strip().isdigit():
            search_terms.append(SupportTicket.id == int(q.strip()))
        query = query.filter(or_(*search_terms))

    tickets = query.order_by(SupportTicket.created_at.desc()).all()

    return SupportTicketListResponse(
        tickets=[_support_ticket_list_item(t) for t in tickets]
    )


@router.get("/support-tickets/overview", response_model=SupportTicketOverviewResponse)
def support_ticket_overview(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == user.id)
        .order_by(SupportTicket.updated_at.desc())
        .all()
    )

    total_tickets = len(tickets)
    workflow_counts = {
        "open": 0,
        "in_review": 0,
        "waiting_for_user": 0,
        "escalated": 0,
        "resolved": 0,
        "closed": 0,
    }
    for ticket in tickets:
        status_key = _support_normalize_status(ticket.status)
        if status_key == "reopen_requested":
            workflow_counts["closed"] += 1
        else:
            workflow_counts[status_key] += 1

    open_tickets = workflow_counts["open"] + workflow_counts["in_review"] + workflow_counts["waiting_for_user"] + workflow_counts["escalated"]
    critical_open_tickets = sum(
        1 for t in tickets
        if _support_normalize_status(t.status) in {"open", "in_review", "waiting_for_user", "escalated"} and (t.priority or "").lower() == "critical"
    )
    security_tickets = sum(1 for t in tickets if (t.category or "").lower() == "security_issue")
    latest_ticket_updated_at = tickets[0].updated_at.isoformat() if tickets and tickets[0].updated_at else None
    smtp_ready = bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD") and (os.getenv("FROM_EMAIL") or os.getenv("SMTP_USER")))

    return SupportTicketOverviewResponse(
        total_tickets=total_tickets,
        open_tickets=open_tickets,
        critical_open_tickets=critical_open_tickets,
        security_tickets=security_tickets,
        latest_ticket_updated_at=latest_ticket_updated_at,
        smtp_ready=smtp_ready,
        workflow_counts=SupportWorkflowCounts(**workflow_counts),
    )


@router.post("/support-tickets", response_model=SupportTicketCreateResponse)
def create_support_ticket(
    data: SupportTicketCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    _support_enforce_rate_limit(user.id, "create_ticket", limit=12)

    priority = data.priority
    if data.category == "security_issue" and priority in {"low", "medium"}:
        priority = "high"

    initial_status = _support_initial_status(data.category, priority)

    ticket = SupportTicket(
        user_id=user.id,
        category=data.category,
        priority=priority,
        subject=data.subject,
        description=data.description,
        contact_email=data.contact_email,
        related_route=data.related_route,
        status=initial_status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    log_audit(
        db,
        user.id,
        "support_ticket_created",
        f"Support ticket SUP-{ticket.id} created ({ticket.category}, {ticket.priority})",
        request,
    )
    db.commit()

    notified = send_support_ticket_notification(
        ticket_id=ticket.id,
        user_email=user.email,
        full_name=user.full_name,
        category=ticket.category,
        priority=ticket.priority,
        subject=ticket.subject,
        description=ticket.description,
        related_route=ticket.related_route or "support",
        contact_email=ticket.contact_email,
    )

    message = "Support ticket submitted successfully."
    if not notified:
        message = "Support ticket saved, but email notification could not be sent right now."

    return SupportTicketCreateResponse(
        success=True,
        message=message,
        ticket=_support_ticket_list_item(ticket),
    )


@router.get("/support-tickets/{ticket_id}", response_model=SupportTicketDetailResponse)
def get_support_ticket_detail(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ticket = db.query(SupportTicket).filter(
        SupportTicket.id == ticket_id,
        SupportTicket.user_id == user.id
    ).first()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Support ticket SUP-{ticket_id} not found"
        )

    messages = (
        db.query(SupportTicketMessage)
        .filter(SupportTicketMessage.ticket_id == ticket.id)
        .order_by(SupportTicketMessage.created_at.asc())
        .all()
    )
    attachments = (
        db.query(SupportTicketAttachment)
        .filter(SupportTicketAttachment.ticket_id == ticket.id)
        .order_by(SupportTicketAttachment.created_at.asc())
        .all()
    )

    return SupportTicketDetailResponse(
        ticket=_support_ticket_list_item(ticket),
        messages=[_support_ticket_message_item(message) for message in messages],
        attachments=[_support_ticket_attachment_item(attachment) for attachment in attachments],
    )


@router.post("/support-tickets/{ticket_id}/messages", response_model=SupportTicketMessageCreateResponse)
def create_support_ticket_message(
    ticket_id: int,
    data: SupportTicketMessageCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    _support_enforce_rate_limit(user.id, "ticket_message", limit=80)

    ticket = db.query(SupportTicket).filter(
        SupportTicket.id == ticket_id,
        SupportTicket.user_id == user.id
    ).first()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Support ticket SUP-{ticket_id} not found"
        )
    if _support_normalize_status(ticket.status) in {"closed", "reopen_requested"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This ticket is locked until support reopens it."
        )

    reply = SupportTicketMessage(
        ticket_id=ticket.id,
        author_user_id=user.id,
        author_type="user",
        message=data.message,
        created_at=datetime.now(timezone.utc),
    )
    db.add(reply)

    if _support_normalize_status(ticket.status) == "waiting_for_user":
        ticket.status = "open"
    ticket.updated_at = datetime.now(timezone.utc)

    log_audit(
        db,
        user.id,
        "support_ticket_replied",
        f"User replied on support ticket SUP-{ticket.id}",
        request,
    )
    db.commit()
    db.refresh(reply)

    return SupportTicketMessageCreateResponse(
        success=True,
        message="Reply sent successfully.",
        reply=_support_ticket_message_item(reply),
    )


@router.post("/support-tickets/{ticket_id}/attachments", response_model=SupportTicketAttachmentCreateResponse)
async def create_support_ticket_attachment(
    ticket_id: int,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    _support_enforce_rate_limit(user.id, "ticket_attachment", limit=40)

    ticket = db.query(SupportTicket).filter(
        SupportTicket.id == ticket_id,
        SupportTicket.user_id == user.id
    ).first()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Support ticket SUP-{ticket_id} not found"
        )
    if _support_normalize_status(ticket.status) in {"closed", "reopen_requested"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This ticket is locked until support reopens it."
        )

    filename = _support_attachment_filename(file.filename or "")
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attachment file is empty"
        )
    if len(content) > MAX_SUPPORT_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attachment exceeds the allowed size limit"
        )
    content_type = _support_validate_attachment_type(filename, content, file.content_type or "")

    attachment = SupportTicketAttachment(
        ticket_id=ticket.id,
        uploaded_by_user_id=user.id,
        uploader_type="user",
        filename=filename,
        content_type=content_type,
        file_size=len(content),
        file_data="",
        storage_ref=support_attachment_write_bytes(ticket.id, filename, content),
        created_at=datetime.now(timezone.utc),
    )
    db.add(attachment)
    ticket.updated_at = datetime.now(timezone.utc)
    log_audit(
        db,
        user.id,
        "support_ticket_attachment_added",
        f"Attachment added to support ticket SUP-{ticket.id}",
        request,
    )
    db.commit()
    db.refresh(attachment)

    return SupportTicketAttachmentCreateResponse(
        success=True,
        message="Attachment uploaded successfully.",
        attachment=_support_ticket_attachment_item(attachment),
    )


@router.post("/support-tickets/{ticket_id}/reopen-request")
def request_support_ticket_reopen(
    ticket_id: int,
    data: SupportTicketReopenRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _support_enforce_rate_limit(user.id, "ticket_reopen_request", limit=20)

    ticket = db.query(SupportTicket).filter(
        SupportTicket.id == ticket_id,
        SupportTicket.user_id == user.id
    ).first()
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Support ticket SUP-{ticket_id} not found"
        )

    current_status = _support_normalize_status(ticket.status)
    if current_status == "reopen_requested":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A reopen request is already pending admin review."
        )
    if current_status != "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only closed tickets can be reopened."
        )

    reason = (data.reason or "").strip()
    now = datetime.now(timezone.utc)

    reopen_message = SupportTicketMessage(
        ticket_id=ticket.id,
        author_user_id=user.id,
        author_type="user",
        message=f"Reopen request reason: {reason}",
        created_at=now,
    )
    db.add(reopen_message)

    ticket.status = "reopen_requested"
    ticket.updated_at = now

    log_audit(
        db,
        user.id,
        "support_ticket_reopen_requested",
        f"User requested reopen for support ticket SUP-{ticket.id}",
        request,
    )
    db.commit()

    return {
        "success": True,
        "message": f"Reopen request submitted for SUP-{ticket.id}. Ticket stays locked until admin reopens it.",
        "ticket_id": ticket.id,
        "status": "reopen_requested",
    }


@router.get("/support-tickets/{ticket_id}/attachments/{attachment_id}/download")
def download_support_ticket_attachment(
    ticket_id: int,
    attachment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket = db.query(SupportTicket).filter(
        SupportTicket.id == ticket_id,
        SupportTicket.user_id == user.id
    ).first()
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Support ticket SUP-{ticket_id} not found"
        )

    attachment = db.query(SupportTicketAttachment).filter(
        SupportTicketAttachment.id == attachment_id,
        SupportTicketAttachment.ticket_id == ticket.id
    ).first()
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found"
        )

    content = support_attachment_read_bytes(attachment)
    if content is None:
        content = b""
    filename = _support_attachment_filename(attachment.filename or "attachment")
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=content,
        media_type=attachment.content_type or "application/octet-stream",
        headers={"Content-Disposition": disposition},
    )


@router.post("/verify-email-change")
def verify_email_change(
    body: VerifyEmailChangeRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    submitted_hash = hashlib.sha256(body.token.encode()).hexdigest()
    now = datetime.utcnow()

    token_row = None
    candidates = db.query(EmailChangeToken).filter(
        EmailChangeToken.used == False,
        EmailChangeToken.expires_at > now
    ).all()
    for candidate in candidates:
        if hmac.compare_digest(candidate.token_hash, submitted_hash):
            token_row = candidate
            break

    if not token_row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token")

    user = db.query(User).filter(User.id == token_row.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification request")

    existing = db.query(User).filter(User.email == token_row.new_email, User.id != user.id).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email address is already in use")

    previous_email = user.email
    user.email = token_row.new_email
    user.updated_at = datetime.utcnow()
    user.token_version = (user.token_version or 0) + 1

    db.query(EmailChangeToken).filter(
        EmailChangeToken.user_id == user.id,
        EmailChangeToken.used == False
    ).update({"used": True})

    log_audit(
        db,
        user.id,
        "email_change_verified",
        f"Email changed from {previous_email} to {user.email}",
        request,
    )
    db.commit()

    try:
        send_email_change_notice(previous_email, user.email)
    except Exception:
        pass

    return {
        "success": True,
        "message": "Email address verified successfully. Please sign in again with your new email address.",
        "email": user.email,
    }


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

def _parse_audit_filter_date(value: Optional[str], is_end: bool = False) -> Optional[datetime]:
    if not value:
        return None
    try:
        if "T" in value:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed

        parsed = datetime.strptime(value, "%Y-%m-%d")
        if is_end:
            parsed = parsed + timedelta(days=1)
        return parsed
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date filter: {value}"
        )


def _audit_event_severity(event_type: str) -> str:
    event_type = (event_type or "").lower()
    if event_type in {"login_blocked_geo", "reauth_failed", "mfa_disabled", "account_deleted"}:
        return "high"
    if event_type in {"login_failed", "password_changed", "email_change_requested", "email_change_verified", "email_change_verification_resent", "email_change_cancelled", "sessions_revoked_all", "session_revoked"}:
        return "medium"
    return "low"


def _severity_event_types(severity: str) -> list[str]:
    severity = (severity or "").lower()
    severity_map = {
        "high": {"login_blocked_geo", "reauth_failed", "mfa_disabled", "account_deleted"},
        "medium": {"login_failed", "password_changed", "email_change_requested", "email_change_verified", "email_change_verification_resent", "email_change_cancelled", "sessions_revoked_all", "session_revoked"},
        "low": {"login", "profile_updated", "ztna_policy_updated", "mfa_enabled", "backup_codes_regenerated", "notification_preferences_updated"},
    }
    return list(severity_map.get(severity, set()))

@router.get("/audit-log")
def get_audit_log(
    limit: int = 50,
    event_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return the current user's security audit log (newest first)."""
    from models import AuditLog
    query = db.query(AuditLog).filter(AuditLog.user_id == user.id)

    if event_type:
        query = query.filter(AuditLog.event_type == event_type.strip().lower())

    if severity:
        matching_types = _severity_event_types(severity)
        if not matching_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid severity filter: {severity}"
            )
        query = query.filter(AuditLog.event_type.in_(matching_types))

    parsed_date_from = _parse_audit_filter_date(date_from)
    parsed_date_to = _parse_audit_filter_date(date_to, is_end=True)
    if parsed_date_from and parsed_date_to and parsed_date_from >= parsed_date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from must be earlier than date_to"
        )
    if parsed_date_from:
        query = query.filter(AuditLog.created_at >= parsed_date_from)
    if parsed_date_to:
        query = query.filter(AuditLog.created_at < parsed_date_to)

    events = query.order_by(AuditLog.created_at.desc()).limit(min(limit, 200)).all()

    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "detail": e.detail,
            "ip_address": e.ip_address,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "severity": _audit_event_severity(e.event_type),
        }
        for e in events
    ]

@router.get("/audit-log/export")
def export_audit_log(
    event_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export the last 90 days of audit logs as a CSV file."""
    from models import AuditLog
    import csv
    import io
    from datetime import datetime, timedelta
    from fastapi.responses import Response

    query = db.query(AuditLog).filter(AuditLog.user_id == user.id)

    if event_type:
        query = query.filter(AuditLog.event_type == event_type.strip().lower())

    if severity:
        matching_types = _severity_event_types(severity)
        if not matching_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid severity filter: {severity}"
            )
        query = query.filter(AuditLog.event_type.in_(matching_types))

    parsed_date_from = _parse_audit_filter_date(date_from)
    parsed_date_to = _parse_audit_filter_date(date_to, is_end=True)
    if parsed_date_from and parsed_date_to and parsed_date_from >= parsed_date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from must be earlier than date_to"
        )
    if parsed_date_from:
        query = query.filter(AuditLog.created_at >= parsed_date_from)
    else:
        query = query.filter(AuditLog.created_at >= (datetime.utcnow() - timedelta(days=90)))

    if parsed_date_to:
        query = query.filter(AuditLog.created_at < parsed_date_to)

    events = query.order_by(AuditLog.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp (UTC)", "Event Type", "Severity", "Detail", "IP Address", "User Agent"])

    for e in events:
        writer.writerow([
            e.created_at.isoformat() if e.created_at else "",
            e.event_type,
            _audit_event_severity(e.event_type),
            "\"" + str(e.detail) + "\"" if e.detail else "",
            e.ip_address or "",
            e.user_agent or ""
        ])

    headers = {
        "Content-Disposition": f"attachment; filename=audit_logs_{user.id}_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    }
    return Response(content=output.getvalue(), media_type="text/csv", headers=headers)


# ============================================================================
# Privacy Translation
# ============================================================================

def _translate_text_fragment(target_locale: str, text: str) -> tuple[str, bool, Optional[str]]:
    if not text.strip():
        return text, True, None

    cache_key = f"{target_locale}:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"
    cached = PRIVACY_TRANSLATION_CACHE.get(cache_key)
    if cached is not None:
        return cached, True, None

    try:
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=auto&tl={quote(target_locale)}&dt=t&q={quote(text)}"
        )
        req = urllib_request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        with urllib_request.urlopen(req, timeout=8) as response:
            payload = response.read().decode("utf-8")
        parsed = json.loads(payload)
        translated = "".join(part[0] for part in parsed[0] if part and part[0])
        if not translated:
            raise ValueError("Empty google translation")
        PRIVACY_TRANSLATION_CACHE[cache_key] = translated
        return translated, True, None
    except Exception as google_exc:
        try:
            fallback_url = (
                "https://api.mymemory.translated.net/get"
                f"?q={quote(text)}&langpair=en|{quote(target_locale)}"
            )
            req = urllib_request.Request(
                fallback_url,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"},
            )
            with urllib_request.urlopen(req, timeout=8) as response:
                payload = response.read().decode("utf-8")
            parsed = json.loads(payload)
            translated = html.unescape(((parsed.get("responseData") or {}).get("translatedText") or "").strip())
            if translated and translated.lower() != text.strip().lower():
                PRIVACY_TRANSLATION_CACHE[cache_key] = translated
                return translated, True, None
        except Exception as mymemory_exc:
            try:
                libre_url = "https://libretranslate.de/translate"
                libre_payload = json.dumps({
                    "q": text,
                    "source": "auto",
                    "target": target_locale,
                    "format": "text",
                }).encode("utf-8")
                libre_req = urllib_request.Request(
                    libre_url,
                    data=libre_payload,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json,text/plain,*/*",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib_request.urlopen(libre_req, timeout=10) as response:
                    payload = response.read().decode("utf-8")
                parsed = json.loads(payload)
                translated = (parsed.get("translatedText") or "").strip()
                if translated and translated.lower() != text.strip().lower():
                    PRIVACY_TRANSLATION_CACHE[cache_key] = translated
                    return translated, True, None
                return text, False, "libretranslate-empty"
            except Exception as libre_exc:
                reason = (
                    f"google={type(google_exc).__name__}; "
                    f"mymemory={type(mymemory_exc).__name__}; "
                    f"libre={type(libre_exc).__name__}"
                )
                return text, False, reason
        return text, False, f"google={type(google_exc).__name__}; mymemory=empty"


@router.post("/privacy/translate", response_model=PrivacyTranslateResponse)
def translate_privacy_text(
    body: PrivacyTranslateRequest,
    user: User = Depends(get_current_user),
):
    if body.target_locale.startswith("en"):
        return PrivacyTranslateResponse(
            target_locale=body.target_locale,
            texts=body.texts,
            provider_available=True,
            provider_message="english-base",
        )

    if is_rate_limited(
        namespace="privacy",
        actor_scope="user",
        actor_id=user.id,
        action="translate",
        limit=PRIVACY_TRANSLATE_RATE_LIMIT,
        window_seconds=PRIVACY_TRANSLATE_WINDOW_SECONDS,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many translation requests. Please try again shortly.",
        )

    translated_texts: list[str] = []
    provider_available = True
    first_reason: Optional[str] = None
    failed_count = 0
    for text in body.texts:
        translated, ok, reason = _translate_text_fragment(body.target_locale, text)
        translated_texts.append(translated)
        if not ok:
            provider_available = False
            failed_count += 1
            if first_reason is None and reason:
                first_reason = reason

    # Keep UX consistent: avoid partial mixed-language pages.
    if failed_count > 0:
        translated_texts = body.texts

    return PrivacyTranslateResponse(
        target_locale=body.target_locale,
        texts=translated_texts,
        provider_available=provider_available,
        provider_message=first_reason,
    )
