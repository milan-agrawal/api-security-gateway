from gateway.cache.redis_client import redis_client

class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        
    def allow_request(self, api_key: str) -> bool:
        # Create a unique Redis key for this user's rate limit
        key = f"rate_limit:{api_key}"
        
        # Check current count
        current_count = redis_client.get(key)
        
        if current_count is None:
            # First request: Set count to 1 and set expiration (TTL)
            redis_client.setex(key, self.window_seconds, 1)
            return True
        
        if int(str(current_count)) < self.max_requests:
            # Increment the counter
            redis_client.incr(key)
            return True
            
        # Limit exceeded
        return False