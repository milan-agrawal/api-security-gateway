from sqlalchemy.orm import Session
from gateway.cache.window_store import get_window_events_ids
from gateway.models import SecurityEvent

def get_window_events(api_key: str, db: Session) -> list[SecurityEvent]:
    """
    Converts Redis window (event IDs) into ORM SecurityEvent objects.
    """
    event_ids = [int(eid) for eid in get_window_events_ids(api_key)]

    if not event_ids:
        return []

    return (
        db.query(SecurityEvent)
        .filter(SecurityEvent.id.in_(event_ids))
        .all()
    )