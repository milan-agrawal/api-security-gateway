import time
from gateway.cache.redis_client import redis_client

WINDOW_SECONDS = 60

def record_events(api_key:str, event_id:int):
    
    key = f"api_window:{api_key}"
    now = time.time()
    
    redis_client.zadd(key,{str(event_id):now})
    
    redis_client.zremrangebyscore(key, 0, now - WINDOW_SECONDS) # Remove old events
    
    redis_client.expire(key, WINDOW_SECONDS + 10) # Set expiration slightly longer than window
    
async def get_window_events_ids(api_key:str) -> list[str]:
    
    key = f"api_key:{api_key}"    
    return await redis_client.zrange(key, 0, -1)