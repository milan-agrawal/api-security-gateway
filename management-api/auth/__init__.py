"""
Auth module for authentication-related endpoints
"""
from .mfa import router as mfa_router

__all__ = ["mfa_router"]
