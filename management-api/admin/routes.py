"""
Admin endpoints for user management
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Header, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func, text as sa_text
from pydantic import BaseModel, EmailStr, validator
from passlib.context import CryptContext
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from collections import defaultdict
import asyncio
import csv
import io
import jwt
import os
import sys
import httpx
import redis
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deps import get_db
from models import User, APIKey, SecurityEvent, AuditLog
from utils import generate_secure_password, send_credentials_email
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
