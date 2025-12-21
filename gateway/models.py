from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime, timezone
from .db import Base

class SecurityEvent(Base):
    __tablename__ = "security_events"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.now(timezone.utc))
    
    client_ip = Column(String, nullable=False)
    api_key = Column(String, nullable=True)
    
    endpoint = Column(String, nullable=False)
    http_method = Column(String, nullable=False )
    
    decision = Column(String, nullable=False)  # "allowed" or "blocked"
    reason = Column(String, nullable=False)  # e.g., "rate limit exceeded", "invalid API key"
    
    status_code = Column(Integer, nullable=False)


    