"""
Admin endpoints for user management
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Header, UploadFile, File, Request, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, text as sa_text, or_
from pydantic import BaseModel, EmailStr, validator
from passlib.context import CryptContext
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from collections import defaultdict
import asyncio
import csv
import base64
import io
import jwt
import os
import sys
import httpx
import redis
import mimetypes
from urllib.parse import quote
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deps import get_db
from models import User, APIKey, SecurityEvent, AuditLog, SupportTicket, SupportTicketMessage, SupportTicketAttachment
from utils import (
    generate_secure_password,
    send_credentials_email,
    send_password_changed_notification,
    send_support_ticket_status_email,
    log_audit,
)
from support_storage import (
    support_attachment_read_bytes,
    support_attachment_safe_filename,
    support_attachment_write_bytes,
)
from rate_limit import is_rate_limited
from db import DATABASE_URL, SessionLocal

router = APIRouter(prefix="/admin", tags=["Admin"])

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Simple rate limiting (in production, use Redis)
# Stores: {admin_email: [timestamp1, timestamp2, ...]}
user_creation_attempts = defaultdict(list)
MAX_USER_CREATIONS_PER_HOUR = 10

# JWT settings - Require SECRET_KEY to be set
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY environment variable is not set. "
        "Please set it in .env file for security."
    )
ALGORITHM = "HS256"
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


# Dependency to verify admin token
def get_current_admin(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Verify JWT token and ensure user is admin"""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing"
        )
    
    try:
        # Extract token from "Bearer <token>"
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format"
            )
        
        token = authorization.split(" ")[1]
        
        # Decode JWT
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        role = payload.get("role")
        
        if not email or role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        # Verify admin exists and is active
        admin = db.query(User).filter(User.email == email, User.role == "admin").first()
        if not admin or not admin.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin account not found or inactive"
            )
        # Enforce token_version for session invalidation
        token_version = payload.get("token_version", 0)
        if getattr(admin, "token_version", 0) != token_version:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked"
            )
        
        return admin
        
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


# Request/Response models
class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str
    role: str  # "user" or "admin"
    enable_2fa: bool = False  # Optional 2FA for users, auto-enabled for admins
    
    # Input validation
    @validator('full_name')
    def validate_full_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Full name cannot be empty')
        if len(v) > 100:
            raise ValueError('Full name cannot exceed 100 characters')
        # Prevent potential email header injection
        if '\n' in v or '\r' in v:
            raise ValueError('Full name cannot contain newline characters')
        return v.strip()
    
    @validator('role')
    def validate_role(cls, v):
        if v not in ['user', 'admin']:
            raise ValueError('Role must be either \"user\" or \"admin\"')
        return v


class UpdateUserRequest(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    
    @validator('full_name')
    def validate_full_name(cls, v):
        if v is not None:
            if len(v.strip()) == 0:
                raise ValueError('Full name cannot be empty')
            if len(v) > 100:
                raise ValueError('Full name cannot exceed 100 characters')
            if '\n' in v or '\r' in v:
                raise ValueError('Full name cannot contain newline characters')
            return v.strip()
        return v

class CreateUserResponse(BaseModel):
    success: bool
    message: str
    user_id: int
    email: str
    role: str
    mfa_enabled: bool  # Whether MFA/2FA is enabled for this account

class UserListItem(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    mfa_enabled: bool
    mfa_setup_complete: bool
    created_at: datetime

class UsersListResponse(BaseModel):
    users: list[UserListItem]
    total: int


class AdminSupportTicketItem(BaseModel):
    id: int
    user_id: int
    user_email: str
    user_full_name: str
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


class AdminSupportTicketMessageItem(BaseModel):
    id: int
    author_type: str
    author_name: str
    author_email: str
    message: str
    created_at: str


class AdminSupportTicketAttachmentItem(BaseModel):
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


class AdminSupportTicketListResponse(BaseModel):
    tickets: list[AdminSupportTicketItem]
    total: int


class AdminSupportTicketOverviewResponse(BaseModel):
    total_tickets: int
    open: int
    in_review: int
    waiting_for_user: int
    escalated: int
    resolved: int
    closed: int


class AdminSupportTicketStatusUpdateRequest(BaseModel):
    status: str

    @validator('status')
    def validate_status(cls, v):
        allowed = {'open', 'in_review', 'waiting_for_user', 'escalated', 'resolved', 'closed'}
        value = (v or '').strip().lower()
        if value not in allowed:
            raise ValueError('Invalid support ticket status')
        return value


class AdminSupportTicketDetailResponse(BaseModel):
    ticket: AdminSupportTicketItem
    messages: list[AdminSupportTicketMessageItem]
    attachments: list[AdminSupportTicketAttachmentItem]


class AdminSupportTicketMessageCreateRequest(BaseModel):
    message: str

    @validator('message')
    def validate_message(cls, v):
        value = (v or '').strip()
        if len(value) < 2:
            raise ValueError('Reply must be at least 2 characters')
        if len(value) > 4000:
            raise ValueError('Reply must be 4000 characters or fewer')
        return value


class AdminSupportTicketMessageCreateResponse(BaseModel):
    success: bool
    message: str
    reply: AdminSupportTicketMessageItem


class AdminSupportTicketAttachmentCreateResponse(BaseModel):
    success: bool
    message: str
    attachment: AdminSupportTicketAttachmentItem


def _support_normalize_status(value: Optional[str]) -> str:
    allowed = {'open', 'in_review', 'waiting_for_user', 'escalated', 'resolved', 'closed', 'reopen_requested'}
    normalized = (value or 'open').strip().lower()
    return normalized if normalized in allowed else 'open'


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
            import json
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


def _support_admin_enforce_rate_limit(actor_id: int, action: str, limit: int, window_seconds: int = 3600):
    blocked = is_rate_limited(
        namespace="support",
        actor_scope="admin",
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


def _admin_support_ticket_item(ticket: SupportTicket, user: User) -> AdminSupportTicketItem:
    return AdminSupportTicketItem(
        id=ticket.id,
        user_id=user.id,
        user_email=user.email,
        user_full_name=user.full_name,
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


def _admin_support_message_item(message: SupportTicketMessage) -> AdminSupportTicketMessageItem:
    author = message.author
    author_type = (message.author_type or "user").lower()
    return AdminSupportTicketMessageItem(
        id=message.id,
        author_type=author_type,
        author_name="User" if author_type == "user" else "Admin",
        author_email="",
        message=message.message,
        created_at=message.created_at.isoformat() if message.created_at else "",
    )


def _admin_support_attachment_item(attachment: SupportTicketAttachment) -> AdminSupportTicketAttachmentItem:
    content_type = attachment.content_type or "application/octet-stream"
    uploader_type = (attachment.uploader_type or "user").lower()
    return AdminSupportTicketAttachmentItem(
        id=attachment.id,
        filename=attachment.filename,
        content_type=content_type,
        file_size=attachment.file_size,
        uploader_type=uploader_type,
        uploader_name="User" if uploader_type == "user" else "Admin",
        uploader_email="",
        created_at=attachment.created_at.isoformat() if attachment.created_at else "",
        download_url=f"/admin/support-tickets/{attachment.ticket_id}/attachments/{attachment.id}/download",
        is_image=content_type.startswith("image/"),
    )


# Background task to activate account after 2 minutes
def activate_account_after_delay(user_id: int):
    """Activate user account after 2 minutes (120 seconds)"""
    import time
    time.sleep(120)  # Wait 2 minutes
    
    # Create new DB session for background task
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.is_active = True
            user.updated_at = datetime.now(timezone.utc)
            db.commit()
            print(f"✓ Account activated for user ID {user_id} ({user.email})")
    except Exception as e:
        print(f"ERROR activating account for user ID {user_id}: {str(e)}")
        db.rollback()
    finally:
        db.close()


# Routes
@router.post("/users/create", response_model=CreateUserResponse)
def create_user(
    request: CreateUserRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Create a new user or admin account (Admin only)
    - Generates secure random password
    - Sends credentials via email
    - Account activated after 2 minutes
    """
    # Rate limiting: Check user creation attempts
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    
    # Clean old attempts
    user_creation_attempts[admin.email] = [
        timestamp for timestamp in user_creation_attempts[admin.email]
        if timestamp > one_hour_ago
    ]
    
    # Check if limit exceeded
    if len(user_creation_attempts[admin.email]) >= MAX_USER_CREATIONS_PER_HOUR:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {MAX_USER_CREATIONS_PER_HOUR} user creations per hour."
        )
    
    # Validate role (already done by Pydantic validator, but keeping for clarity)
    if request.role not in ["user", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'user' or 'admin'"
        )
    
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email {request.email} already exists"
        )
    
    # Generate secure password
    plain_password = generate_secure_password(12)
    password_hash = pwd_context.hash(plain_password)
    
    # Determine if MFA should be enabled
    # - Admins: MFA is MANDATORY (always enabled)
    # - Users: MFA is optional (based on enable_2fa checkbox)
    mfa_enabled = request.role == "admin" or request.enable_2fa
    
    # Create user with is_active=False
    new_user = User(
        email=request.email,
        password_hash=password_hash,
        full_name=request.full_name,
        role=request.role,
        is_active=False,  # Will be activated after 2 minutes
        mfa_enabled=mfa_enabled,  # Set MFA status
        mfa_setup_complete=False,  # User must complete setup on first login
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Send credentials email in background (avoid blocking the response)
    background_tasks.add_task(
        send_credentials_email,
        recipient_email=request.email,
        full_name=request.full_name,
        password=plain_password,
        role=request.role,
        mfa_enabled=mfa_enabled
    )
    
    # Schedule account activation for 2 minutes later
    background_tasks.add_task(
        activate_account_after_delay,
        new_user.id
    )
    
    # Track successful creation for rate limiting
    user_creation_attempts[admin.email].append(now)
    
    # Build response message
    mfa_info = ""
    if mfa_enabled:
        if request.role == "admin":
            mfa_info = " MFA is mandatory - setup required on first login."
        else:
            mfa_info = " 2FA is enabled - setup required on first login."
    
    return CreateUserResponse(
        success=True,
        message=f"{request.role.capitalize()} account created. Credentials sent to {request.email}. Account will be activated in 2 minutes.{mfa_info}",
        user_id=new_user.id,
        email=new_user.email,
        role=new_user.role,
        mfa_enabled=mfa_enabled
    )


@router.get("/users/list", response_model=UsersListResponse)
def list_users(
    role: str = None,  # Optional filter: "user" or "admin"
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    List all users or filter by role (Admin only)
    Query params:
    - role: Optional filter ("user" or "admin")
    """
    query = db.query(User)
    
    # Apply role filter if provided
    if role:
        if role not in ["user", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role filter must be 'user' or 'admin'"
            )
        query = query.filter(User.role == role)
    
    # Get users ordered by creation date (newest first)
    users = query.order_by(User.created_at.desc()).all()
    
    return UsersListResponse(
        users=[
            UserListItem(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                role=user.role,
                is_active=user.is_active,
                mfa_enabled=user.mfa_enabled,
                mfa_setup_complete=user.mfa_setup_complete,
                created_at=user.created_at
            )
            for user in users
        ],
        total=len(users)
    )


@router.get("/users/{user_id}")
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Get detailed user info by ID (Admin only).
    Returns profile, MFA status, API key count, and last login.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )

    api_keys_count = db.query(APIKey).filter(APIKey.user_id == user_id).count()
    active_keys = db.query(APIKey).filter(APIKey.user_id == user_id, APIKey.is_active == True).count()

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "mfa_enabled": user.mfa_enabled,
        "mfa_setup_complete": user.mfa_setup_complete,
        "api_keys_count": api_keys_count,
        "active_api_keys": active_keys
    }


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Delete a user by ID (Admin only)
    Cannot delete yourself
    """
    # Get user to delete
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # Prevent self-deletion
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    # Delete user
    db.delete(user)
    db.commit()
    
    return {
        "success": True,
        "message": f"User {user.email} deleted successfully"
    }


@router.patch("/users/{user_id}/toggle-status")
def toggle_user_status(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Toggle user active/inactive status (Admin only)
    Cannot deactivate yourself
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # Prevent self-deactivation
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )
    
    # Toggle status
    user.is_active = not user.is_active
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    
    return {
        "success": True,
        "message": f"User {user.email} is now {'active' if user.is_active else 'inactive'}",
        "is_active": user.is_active
    }


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    request: UpdateUserRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Update user profile (email, full_name) by ID (Admin only)
    Only provided fields are updated.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    changes = []
    
    # Update email if provided and different
    if request.email is not None and request.email != user.email:
        # Check if new email is already taken
        existing = db.query(User).filter(User.email == request.email, User.id != user_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email {request.email} is already in use"
            )
        old_email = user.email
        user.email = request.email
        changes.append(f"email changed from {old_email} to {request.email}")
    
    # Update full_name if provided and different
    if request.full_name is not None and request.full_name != user.full_name:
        user.full_name = request.full_name
        changes.append(f"name updated to {request.full_name}")
    
    if not changes:
        return {
            "success": True,
            "message": "No changes were made"
        }
    
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    
    return {
        "success": True,
        "message": f"User updated: {'; '.join(changes)}",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role
        }
    }


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Admin-triggered password reset for a user.
    Generates a new secure password, emails it, and invalidates existing sessions.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # Prevent resetting own password through this endpoint
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reset your own password through this endpoint. Use the profile settings instead."
        )
    
    # Generate new secure password
    new_password = generate_secure_password(14)
    user.password_hash = pwd_context.hash(new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    
    # Increment token_version to invalidate all existing sessions/JWTs
    user.token_version = (user.token_version or 0) + 1
    user.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    
    # Send new credentials via email in background
    background_tasks.add_task(
        send_credentials_email,
        recipient_email=user.email,
        full_name=user.full_name,
        password=new_password,
        role=user.role,
        mfa_enabled=user.mfa_enabled
    )

    if getattr(user, "password_change_alert_enabled", True):
        background_tasks.add_task(
            send_password_changed_notification,
            user.email,
            "Admin reset"
        )
    
    return {
        "success": True,
        "message": f"Password reset for {user.email}. New credentials sent via email. All existing sessions have been invalidated."
    }


@router.post("/users/{user_id}/revoke-sessions")
def revoke_user_sessions(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Force logout a user by incrementing their token_version.
    All existing JWTs become invalid immediately.
    """
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )

    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke your own sessions through this endpoint"
        )

    user.token_version = (user.token_version or 0) + 1
    user.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "success": True,
        "message": f"All sessions revoked for {user.email}. They will need to log in again."
    }


@router.get("/users/{user_id}/activity")
def get_user_activity(
    user_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Get a user's API activity from gateway security logs.
    Joins the user's API keys with security_events to show request history.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )

    # Get all API key values belonging to this user
    key_rows = db.query(APIKey.key_value).filter(APIKey.user_id == user_id).all()
    key_values = [k[0] for k in key_rows]

    if not key_values:
        return {
            "events": [],
            "summary": {
                "total_requests": 0,
                "allowed": 0,
                "blocked": 0,
                "unique_endpoints": 0,
                "last_activity": None
            },
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None
        }

    # Summary stats
    total = db.query(func.count(SecurityEvent.id)).filter(
        SecurityEvent.api_key.in_(key_values)
    ).scalar() or 0

    allowed = db.query(func.count(SecurityEvent.id)).filter(
        SecurityEvent.api_key.in_(key_values),
        SecurityEvent.decision == "allowed"
    ).scalar() or 0

    blocked = total - allowed

    unique_endpoints = db.query(func.count(func.distinct(SecurityEvent.endpoint))).filter(
        SecurityEvent.api_key.in_(key_values)
    ).scalar() or 0

    # Recent events (newest first)
    events = db.query(SecurityEvent).filter(
        SecurityEvent.api_key.in_(key_values)
    ).order_by(SecurityEvent.timestamp.desc()).limit(min(limit, 100)).all()

    last_activity = events[0].timestamp.isoformat() if events else None

    return {
        "events": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "endpoint": e.endpoint,
                "http_method": e.http_method,
                "decision": e.decision,
                "reason": e.reason,
                "status_code": e.status_code,
                "client_ip": e.client_ip
            }
            for e in events
        ],
        "summary": {
            "total_requests": total,
            "allowed": allowed,
            "blocked": blocked,
            "unique_endpoints": unique_endpoints,
            "last_activity": last_activity
        },
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None
    }


@router.get("/support-tickets", response_model=AdminSupportTicketListResponse)
def list_support_tickets(
    q: Optional[str] = Query(None),
    status_filter: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    query = db.query(SupportTicket, User).join(User, SupportTicket.user_id == User.id)

    if q:
        search = f"%{q.strip()}%"
        search_terms = [
            SupportTicket.subject.ilike(search),
            SupportTicket.description.ilike(search),
            SupportTicket.contact_email.ilike(search),
            SupportTicket.related_route.ilike(search),
            SupportTicket.category.ilike(search),
            SupportTicket.status.ilike(search),
            User.email.ilike(search),
            User.full_name.ilike(search),
        ]
        if q.strip().isdigit():
            search_terms.append(SupportTicket.id == int(q.strip()))
        query = query.filter(or_(*search_terms))
    if status_filter:
        query = query.filter(SupportTicket.status == _support_normalize_status(status_filter))
    if category:
        query = query.filter(SupportTicket.category == category.strip().lower())
    if priority:
        query = query.filter(SupportTicket.priority == priority.strip().lower())

    rows = query.order_by(SupportTicket.updated_at.desc()).all()

    tickets = [_admin_support_ticket_item(ticket, user) for ticket, user in rows]

    return AdminSupportTicketListResponse(tickets=tickets, total=len(tickets))


@router.get("/support-tickets/overview", response_model=AdminSupportTicketOverviewResponse)
def support_ticket_overview(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    tickets = db.query(SupportTicket).all()
    counts = {
        'open': 0,
        'in_review': 0,
        'waiting_for_user': 0,
        'escalated': 0,
        'resolved': 0,
        'closed': 0,
    }
    for ticket in tickets:
        status_key = _support_normalize_status(ticket.status)
        if status_key == 'reopen_requested':
            counts['closed'] += 1
        else:
            counts[status_key] += 1

    return AdminSupportTicketOverviewResponse(
        total_tickets=len(tickets),
        open=counts['open'],
        in_review=counts['in_review'],
        waiting_for_user=counts['waiting_for_user'],
        escalated=counts['escalated'],
        resolved=counts['resolved'],
        closed=counts['closed'],
    )


@router.get("/support-tickets/{ticket_id}", response_model=AdminSupportTicketDetailResponse)
def get_support_ticket_detail(
    ticket_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    row = (
        db.query(SupportTicket, User)
        .join(User, SupportTicket.user_id == User.id)
        .filter(SupportTicket.id == ticket_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Support ticket SUP-{ticket_id} not found"
        )

    ticket, user = row
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

    return AdminSupportTicketDetailResponse(
        ticket=_admin_support_ticket_item(ticket, user),
        messages=[_admin_support_message_item(message) for message in messages],
        attachments=[_admin_support_attachment_item(attachment) for attachment in attachments],
    )


@router.post("/support-tickets/{ticket_id}/messages", response_model=AdminSupportTicketMessageCreateResponse)
def create_support_ticket_message(
    ticket_id: int,
    body: AdminSupportTicketMessageCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    _support_admin_enforce_rate_limit(admin.id, "ticket_message", limit=120)

    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Support ticket SUP-{ticket_id} not found"
        )
    if _support_normalize_status(ticket.status) in {"closed", "reopen_requested"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This ticket is locked until an admin reopens it."
        )

    reply = SupportTicketMessage(
        ticket_id=ticket.id,
        author_user_id=admin.id,
        author_type="admin",
        message=body.message,
        created_at=datetime.now(timezone.utc),
    )
    db.add(reply)
    ticket.updated_at = datetime.now(timezone.utc)
    if _support_normalize_status(ticket.status) == "open":
        ticket.status = "in_review"

    log_audit(
        db,
        admin.id,
        "support_ticket_admin_replied",
        f"Admin replied on support ticket SUP-{ticket.id}",
        request,
    )
    db.commit()
    db.refresh(reply)

    return AdminSupportTicketMessageCreateResponse(
        success=True,
        message="Reply sent successfully.",
        reply=_admin_support_message_item(reply),
    )


@router.post("/support-tickets/{ticket_id}/attachments", response_model=AdminSupportTicketAttachmentCreateResponse)
async def create_support_ticket_attachment(
    ticket_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    _support_admin_enforce_rate_limit(admin.id, "ticket_attachment", limit=80)

    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Support ticket SUP-{ticket_id} not found"
        )
    if _support_normalize_status(ticket.status) in {"closed", "reopen_requested"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This ticket is locked until an admin reopens it."
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
        uploaded_by_user_id=admin.id,
        uploader_type="admin",
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
        admin.id,
        "support_ticket_attachment_added",
        f"Admin added attachment to support ticket SUP-{ticket.id}",
        request,
    )
    db.commit()
    db.refresh(attachment)

    return AdminSupportTicketAttachmentCreateResponse(
        success=True,
        message="Attachment uploaded successfully.",
        attachment=_admin_support_attachment_item(attachment),
    )


@router.get("/support-tickets/{ticket_id}/attachments/{attachment_id}/download")
def download_support_ticket_attachment(
    ticket_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
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


@router.patch("/support-tickets/{ticket_id}")
def update_support_ticket_status(
    ticket_id: int,
    body: AdminSupportTicketStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    _support_admin_enforce_rate_limit(admin.id, "ticket_status_update", limit=240)

    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Support ticket SUP-{ticket_id} not found"
        )

    new_status = _support_normalize_status(body.status)
    old_status = _support_normalize_status(ticket.status)
    if old_status == new_status:
        return {
            "success": True,
            "message": f"Support ticket SUP-{ticket.id} is already {new_status.replace('_', ' ')}",
            "ticket_id": ticket.id,
            "status": new_status,
        }
    if old_status == "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Closed tickets are locked. Wait for a user reopen request first."
        )

    ticket.status = new_status
    ticket.updated_at = datetime.now(timezone.utc)

    log_audit(
        db,
        admin.id,
        "support_ticket_status_updated",
        f"Support ticket SUP-{ticket.id} status changed from {old_status} to {new_status}",
        request,
    )
    db.commit()

    try:
        send_support_ticket_status_email(
            recipient_email=ticket.user.email,
            full_name=ticket.user.full_name if ticket.user else "",
            ticket_id=ticket.id,
            subject=ticket.subject,
            old_status=old_status,
            new_status=new_status,
        )
    except Exception:
        pass

    return {
        "success": True,
        "message": f"Support ticket SUP-{ticket.id} moved to {new_status.replace('_', ' ')}",
        "ticket_id": ticket.id,
        "status": new_status,
    }


@router.post("/users/import-csv")
async def import_users_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Bulk import users from a CSV file.
    CSV columns: email, full_name, role (optional, defaults to 'user'), enable_2fa (optional, defaults to false)
    """
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .csv files are accepted"
        )

    # Read file content
    try:
        content = await file.read()
        text = content.decode('utf-8-sig')  # Handle BOM
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be UTF-8 encoded"
        )

    reader = csv.DictReader(io.StringIO(text))

    # Validate headers
    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is empty or has no headers"
        )

    required_fields = {'email', 'full_name'}
    headers_lower = {h.strip().lower() for h in reader.fieldnames}
    missing = required_fields - headers_lower
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required CSV columns: {', '.join(missing)}. Required: email, full_name"
        )

    # Normalize header mapping
    header_map = {h.strip().lower(): h for h in reader.fieldnames}

    results = {"created": [], "skipped": [], "errors": []}
    row_num = 1  # Start after header

    for row in reader:
        row_num += 1
        # Get values using normalized headers
        email = row.get(header_map.get('email', ''), '').strip().lower()
        full_name = row.get(header_map.get('full_name', ''), '').strip()
        role = row.get(header_map.get('role', ''), 'user').strip().lower() or 'user'
        enable_2fa_str = row.get(header_map.get('enable_2fa', ''), 'false').strip().lower()

        # Validate email
        if not email or '@' not in email:
            results["errors"].append({"row": row_num, "email": email or '(empty)', "reason": "Invalid email"})
            continue

        # Validate full_name
        if not full_name:
            results["errors"].append({"row": row_num, "email": email, "reason": "Full name is empty"})
            continue

        if len(full_name) > 100:
            results["errors"].append({"row": row_num, "email": email, "reason": "Full name exceeds 100 chars"})
            continue

        # Validate role
        if role not in ('user', 'admin'):
            results["errors"].append({"row": row_num, "email": email, "reason": f"Invalid role '{role}'"})
            continue

        # Check duplicate in DB
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            results["skipped"].append({"row": row_num, "email": email, "reason": "Email already exists"})
            continue

        # Determine 2FA
        enable_2fa = enable_2fa_str in ('true', '1', 'yes')
        mfa_enabled = role == 'admin' or enable_2fa

        # Generate password and create user
        plain_password = generate_secure_password(12)
        password_hash = pwd_context.hash(plain_password)

        new_user = User(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            role=role,
            is_active=True,
            mfa_enabled=mfa_enabled,
            mfa_setup_complete=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(new_user)

        try:
            db.flush()  # Get ID without committing yet
            results["created"].append({
                "row": row_num,
                "email": email,
                "full_name": full_name,
                "role": role,
                "user_id": new_user.id
            })
            # Send credentials email (best effort, don't block)
            try:
                send_credentials_email(
                    recipient_email=email,
                    full_name=full_name,
                    password=plain_password,
                    role=role,
                    mfa_enabled=mfa_enabled
                )
            except Exception:
                pass  # Email failure shouldn't block import
        except Exception as e:
            db.rollback()
            results["errors"].append({"row": row_num, "email": email, "reason": str(e)})
            continue

    # Commit all successfully created users
    if results["created"]:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            return {
                "success": False,
                "message": f"Database commit failed: {str(e)}",
                "created": 0,
                "skipped": len(results["skipped"]),
                "errors": len(results["errors"]) + len(results["created"]),
                "details": results
            }

    return {
        "success": True,
        "message": f"Import complete: {len(results['created'])} created, {len(results['skipped'])} skipped, {len(results['errors'])} errors",
        "created": len(results["created"]),
        "skipped": len(results["skipped"]),
        "errors": len(results["errors"]),
        "details": results
    }


# ============================================================
# SYSTEM STATUS - Health check for all services
# ============================================================

SERVICE_ENDPOINTS = {
    "gateway": "http://127.0.0.1:8000/health",
    "backend": "http://127.0.0.1:9000/health",
    "management": "http://127.0.0.1:8001/health",
}

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


@router.get("/system-status")
async def system_status(admin: User = Depends(get_current_admin)):
    """Check health of all backend services, database, and Redis."""
    services = {}

    # Check HTTP services concurrently
    async with httpx.AsyncClient(timeout=3.0) as client:
        async def check_service(name: str, url: str):
            try:
                resp = await client.get(url)
                services[name] = "online" if resp.status_code == 200 else "offline"
            except Exception:
                services[name] = "offline"

        await asyncio.gather(
            *[check_service(name, url) for name, url in SERVICE_ENDPOINTS.items()]
        )

    # Check Database
    try:
        db = SessionLocal()
        db.execute(sa_text("SELECT 1"))
        db.close()
        services["database"] = "online"
    except Exception:
        services["database"] = "offline"

    # Check Redis
    try:
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
        r.ping()
        r.close()
        services["redis"] = "online"
    except Exception:
        services["redis"] = "offline"

    # Determine overall status
    online_count = sum(1 for s in services.values() if s == "online")
    total = len(services)

    if online_count == total:
        overall = "operational"
    elif online_count == 0:
        overall = "offline"
    else:
        overall = "degraded"

    return {
        "overall": overall,
        "services": services,
        "online": online_count,
        "total": total
    }


@router.get("/users/{user_id}/audit-log")
def get_user_audit_log(
    user_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """Return a user's security audit log (newest first). Admin-only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )

    events = (
        db.query(AuditLog)
        .filter(AuditLog.user_id == user_id)
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
