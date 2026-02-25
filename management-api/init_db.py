from .db import engine, Base
from .models import User, APIKey

def init_database():
    """Create all tables in the database"""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✓ Tables created successfully!")
    print("  - users")
    print("  - api_keys")

if __name__ == "__main__":
    init_database()
