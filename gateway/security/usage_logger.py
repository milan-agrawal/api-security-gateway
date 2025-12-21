import time

def log_request(api_key, endpoint:str, allowed:bool):
    log_entry = {
        "timestamp": time.time(),
        "api_key": api_key,
        "endpoint": endpoint,
        "allowed": allowed
    }
    print(log_entry)