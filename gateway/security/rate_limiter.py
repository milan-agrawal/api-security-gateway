import time
from collections import defaultdict

class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clients = defaultdict( lambda:{    
            "count":0,  
            "window_start": time.time()
        })
        
    def allow_request(self, api_key) -> bool:
        now = time.time()
        client = self.clients[api_key]
        
        if now - client["window_start"] > self.window_seconds:
            client["count"] = 0
            client["window_start"] = now
            
        client["count"] += 1
        
        if client["count"] > self.max_requests:
            return False
        
        return True