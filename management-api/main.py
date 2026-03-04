from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
import jwt
import os

from db import engine, Base
from models import User
from deps import get_db
from admin import router as admin_router
from auth.mfa import router as mfa_router, create_mfa_temp_token
from auth.password_reset import router as password_reset_router

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Management API", version="1.0.0")

# Include routers
app.include_router(admin_router)
app.include_router(mfa_router)
app.include_router(password_reset_router)

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

# Helper functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, token_version: int = 0) -> str:
    """Create JWT access token and include token_version for session invalidation."""
    to_encode = data.copy()
    to_encode.update({"token_version": token_version})
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Routes
@app.get("/")
def root():
    return {
        "service": "Management API",
        "version": "1.0.0",
        "status": "running"
    }

@app.post("/auth/login", response_model=LoginResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
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
    
    # Verify password
    if not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled"
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
    
    # No MFA - create full JWT token
    token_data = {
        "sub": user.email,
        "role": user.role,
        "user_id": user.id
    }
    token = create_access_token(token_data, token_version=user.token_version)
    
    return LoginResponse(
        token=token,
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
