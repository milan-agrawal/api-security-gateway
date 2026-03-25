import logging
import time

logger = logging.getLogger(__name__)

def log_request(api_key, endpoint:str, allowed:bool):
    log_entry = {
        "timestamp": time.time(),
        "api_key": api_key,
        "endpoint": endpoint,
        "allowed": allowed
    }
    logger.info("gateway_request %s", log_entry)
