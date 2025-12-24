from sqlalchemy import Column, Integer, String, DateTime
from gateway.models import Base  # Reuse existing Base from gateway
from datetime import datetime

class BackendEvent(Base):
    __tablename__ = "backend_events"

    id = Column(Integer, primary_key=True)
    request_id = Column(String, index=True)
    endpoint = Column(String)
    method = Column(String)
    status_code = Column(Integer)
    latency_ms = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)