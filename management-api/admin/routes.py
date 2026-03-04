"""
Admin endpoints for user management
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, validator
from passlib.context import CryptContext
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import defaultdict
import asyncio
import jwt
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deps import get_db
from models import User
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
                created_at=user.created_at
            )
            for user in users
        ],
        total=len(users)
    )


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
