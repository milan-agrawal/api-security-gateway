import hashlib
import os
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.orm import Session

load_dotenv()


def get_gateway_shared_secret() -> str:
    jwt_secret = os.getenv("JWT_SECRET_KEY")
    if not jwt_secret:
        raise RuntimeError("JWT_SECRET_KEY environment variable is not set")
    return hashlib.sha256(f"{jwt_secret}:gateway-shared-v1".encode("utf-8")).hexdigest()


def get_active_api_key_record(db: Session, api_key: Optional[str]) -> Optional[dict]:
    value = (api_key or "").strip()
    if not value:
        return None

    row = db.execute(
        text(
            """
            SELECT id, user_id, key_name, rate_limit
            FROM api_keys
            WHERE key_value = :key_value
              AND is_active = true
              AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            LIMIT 1
            """
        ),
        {"key_value": value},
    ).mappings().first()

    return dict(row) if row else None
