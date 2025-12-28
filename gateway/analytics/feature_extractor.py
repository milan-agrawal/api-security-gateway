from collections import Counter
from math import log2
from statistics import variance
from typing import List
from datetime import datetime
from gateway.models import SecurityEvent

WINDOW_SECONDS = 60

def extract_features(events: List[SecurityEvent]) -> dict:
    if not events:
        return {}
    
    total_requests = len(events)
    endpoints = [e.endpoint for e in events]
    unique_endpoints = len(set(endpoints))
    
    # Sort events by timestamp to calculate inter-arrival times
    timestamps = sorted(e.timestamp for e in events)
    
    if len(timestamps) > 1:
        # CORRECTED MATH: Subtract timestamps first, then get total_seconds
        inter_arrivals = [
            (timestamps[i] - timestamps[i-1]).total_seconds() 
            for i in range(1, len(timestamps))
        ]
        # Avoid variance error if we only have 1 interval
        inter_arrivals_variance = variance(inter_arrivals) if len(inter_arrivals) > 1 else 0.0    
    else:
        inter_arrivals_variance = 0.0
        
    requests_per_second = total_requests / WINDOW_SECONDS
    
    endpoints_counts = Counter(endpoints)
    entropy = 0.0
    for count in endpoints_counts.values():
        p = count / total_requests
        entropy -= p * log2(p)
        
    blocked = sum(1 for e in events if str(e.decision) == "BLOCK")
    blocked_ratio = blocked / total_requests
    
    throttled = sum(1 for e in events if str(e.decision) == "THROTTLE")
    throttled_ratio = throttled / total_requests
     
    return {
        "total_requests": total_requests,
        "unique_endpoints": unique_endpoints,
        "inter_arrivals_variance": round(inter_arrivals_variance, 3),
        "requests_per_second": round(requests_per_second, 6),
        "endpoints_entropy": round(entropy, 6),
        "blocked_ratio": round(blocked_ratio, 3),
        "throttled_ratio": round(throttled_ratio, 3),
    }