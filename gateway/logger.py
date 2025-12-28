from sqlalchemy.orm import Session

from gateway import db
from .models import SecurityEvent

def log_security_event(
    db:Session,
    client_ip:str,
    api_key:str|None,
    endpoint:str,
    http_method:str,
    decision:str,
    reason:str,
    status_code:int
):
    event = SecurityEvent(
        client_ip=client_ip,
        api_key=api_key,
        endpoint=endpoint,
        http_method=http_method,
        decision=decision,
        reason=reason,
        status_code=status_code
    )
    
    db.add(event)
    db.commit()
    db.refresh(event)
    return event.id