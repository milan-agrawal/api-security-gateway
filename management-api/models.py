from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from db import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user")  # "user" or "admin"
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc), nullable=False)
    
    # MFA/2FA fields
    mfa_enabled = Column(Boolean, default=False, nullable=False)  # Is MFA/2FA enabled
    mfa_secret = Column(String, nullable=True)  # TOTP secret key (encrypted)
    mfa_setup_complete = Column(Boolean, default=False, nullable=False)  # Has user completed setup
    mfa_backup_codes = Column(Text, nullable=True)  # JSON array of hashed backup codes
    password_changed_at = Column(DateTime, nullable=True)  # Last password change timestamp
    token_version = Column(Integer, default=0, nullable=False)  # Increment to invalidate JWTs
    last_login_at = Column(DateTime, nullable=True)  # Last successful login timestamp
    avatar = Column(Text, nullable=True)  # Base64 Data URL for profile picture
    failed_login_attempts = Column(Integer, default=0, nullable=False)  # Failed login counter
    locked_until = Column(DateTime, nullable=True)  # Account lockout timestamp
    allowed_countries = Column(String, nullable=True)  # Comma-separated list of allowed countries (ZTNA)
    
    # Relationship to API keys
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    # Relationship to password reset tokens
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")
    # Relationship to sessions
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")


class APIKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    key_value = Column(String, unique=True, nullable=False, index=True)
    key_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    rate_limit = Column(Integer, default=100, nullable=False)  # requests per minute
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=True)  # NULL means no expiration
    
    # Relationship to user
    user = relationship("User", back_populates="api_keys")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    request_ip = Column(String, nullable=True)
    request_user_agent = Column(String, nullable=True)

    user = relationship("User")


class SecurityEvent(Base):
    """Read-only mirror of the gateway's security_events table for admin analytics."""
    __tablename__ = "security_events"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.now(timezone.utc))
    client_ip = Column(String, nullable=False)
    api_key = Column(String, nullable=True)
    endpoint = Column(String, nullable=False)
    http_method = Column(String, nullable=False)
    decision = Column(String, nullable=False)
    reason = Column(String, nullable=False)
    status_code = Column(Integer, nullable=False)


class UserSession(Base):
    """Tracks individual login sessions for device management."""
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_token = Column(String, unique=True, nullable=False, index=True)  # UUID stored in JWT
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    device_label = Column(String, nullable=True)  # Parsed: "Chrome on Windows"
    country = Column(String, nullable=True)
    city = Column(String, nullable=True)
    is_new_location = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    last_active_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="sessions")


class AuditLog(Base):
    """Records security-relevant account events (login, password change, MFA, etc.)."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    detail = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False, index=True)

    user = relationship("User")


class IpGeoCache(Base):
    """Caches IP geolocation data to avoid hitting external APIs multiple times for the same IP."""
    __tablename__ = "ip_geo_cache"

    ip_address = Column(String, primary_key=True, index=True)
    country = Column(String, nullable=True)
    city = Column(String, nullable=True)
    region = Column(String, nullable=True)
    country_code = Column(String, nullable=True)
    latitude = Column(String, nullable=True)  # Using String/Float depends, String is safe for API parity
    longitude = Column(String, nullable=True)
    isp = Column(String, nullable=True)
    looked_up_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
