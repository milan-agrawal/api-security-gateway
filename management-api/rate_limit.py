from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, timedelta
import os
import threading

import redis


_LOCK = threading.Lock()
_IN_MEMORY_EVENTS = defaultdict(list)
_REDIS_CLIENT = None


def _get_redis_client():
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT

    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        return None

    try:
        _REDIS_CLIENT = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        _REDIS_CLIENT.ping()
        return _REDIS_CLIENT
    except Exception:
        _REDIS_CLIENT = None
        return None


def is_rate_limited(
    *,
    namespace: str,
    actor_scope: str,
    actor_id: int | str,
    action: str,
    limit: int,
    window_seconds: int = 3600,
) -> bool:
    """
    Returns True if the action should be blocked by rate limit.
    Redis-backed when REDIS_URL is configured and reachable; otherwise falls back
    to in-memory per-process counters.
    """
    actor = str(actor_id)
    key = f"ratelimit:{namespace}:{actor_scope}:{actor}:{action}"

    client = _get_redis_client()
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.incr(key, 1)
            pipe.ttl(key)
            current, ttl = pipe.execute()
            if int(current) == 1 or int(ttl) < 0:
                client.expire(key, int(window_seconds))
            return int(current) > int(limit)
        except Exception:
            # Fail open to local fallback if Redis is temporarily unavailable.
            pass

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)
    with _LOCK:
        events = [ts for ts in _IN_MEMORY_EVENTS[key] if ts > cutoff]
        blocked = len(events) >= int(limit)
        if not blocked:
            events.append(now)
        _IN_MEMORY_EVENTS[key] = events
    return blocked
