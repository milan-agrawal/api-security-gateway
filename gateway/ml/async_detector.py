import asyncio
import numpy as np 
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session

from gateway.db import SessionLocal
from gateway.analytics.feature_extractor import extract_features
from gateway.analytics.window_materializer import get_window_events
from gateway.logger import log_security_event
from gateway.cache.redis_client import redis_client # <--- NEW IMPORT

def analyze_behaviour(api_key: str, model: IsolationForest):
    db = SessionLocal()
    try:
        events = get_window_events(api_key, db)
        if len(events) < 3: 
            return 
        
        features_dict = extract_features(events)
        if not features_dict:
            return

        X = np.array([list(features_dict.values())])
        score = model.decision_function(X)[0]
        
        # Decision logic
        decision = "ANOMALY" if score < -0.2 else "NORMAL"
        
        if decision == "ANOMALY":
            # --- NEW BLOCKING LOGIC START ---
            print(f"🚨 ML DETECTED ANOMALY for {api_key}! Blocking for 5 minutes.")
            
            # Ban user in Redis for 300 seconds (5 mins)
            block_key = f"blocked:{api_key}"
            redis_client.setex(block_key, 300, "true")
            
            reason_msg = f"ASYNC_ML_DETECTION (Score: {score:.3f}) - BLOCKED"
            # --- NEW BLOCKING LOGIC END ---
        else:
            reason_msg = f"ASYNC_ML_DETECTION (Score: {score:.3f})"

        # Log the result
        if decision == "ANOMALY":
            log_security_event(
                db=db,
                client_ip="ml-engine",
                api_key=api_key,
                endpoint="*",
                http_method="*",
                decision=decision,
                reason=reason_msg,
                status_code=200
            )
            
    except Exception as e:
        print(f"ML Analysis Error: {e}")
    finally:
        db.close()

def schedule_behavior_analysis(api_key: str, db: Session, model):
    asyncio.create_task(asyncio.to_thread(analyze_behaviour, api_key, model))