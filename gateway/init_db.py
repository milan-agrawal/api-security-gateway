from .db import engine
from .models import Base
# Import backend models so they're registered with Base.metadata
from backend_api.models import BackendEvent

def init_db():
    Base.metadata.create_all(bind=engine)