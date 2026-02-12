import asyncio
import numpy as np 
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session

from gateway.db import SessionLocal  # Import the session factory
from gateway.analytics.feature_extractor import extract_features
from gateway.analytics.window_materializer import get_window_events
from gateway.logger import log_security_event

def analyze_behaviour(api_key: str, model: IsolationForest):
    # Create a NEW database session specifically for this background task
    db = SessionLocal()
    try:
        events = get_window_events(api_key, db)
        if len(events) < 3: # Need at least a few events to calculate variance
            return 
        
        features_dict = extract_features(events)
        
        # If feature extraction failed or returned empty
        if not features_dict:
            return

        X = np.array([list(features_dict.values())])
        score = model.decision_function(X)[0]
        
        # Decision logic
        decision = "ANOMALY" if score < -0.2 else "NORMAL"
        
        # Only log if it is actually an anomaly (to save DB space) 
        # or log everything if you want full visibility.
        if decision == "ANOMALY":
            log_security_event(
                db=db,
                client_ip="ml-engine",
                api_key=api_key,
                endpoint="*",
                http_method="*",
                decision=decision,
                reason=f"ASYNC_ML_DETECTION (Score: {score:.3f})",
                status_code=200
            )
            print(f"Example ML Alert: API Key {api_key} flagged as ANOMALY")
            
    except Exception as e:
        print(f"ML Analysis Error: {e}")
    finally:
        db.close() # Always close the session!

def schedule_behavior_analysis(api_key: str, db: Session, model):
    # We do NOT pass 'db' to the thread. We only pass the key and model.
    asyncio.create_task(asyncio.to_thread(analyze_behaviour, api_key, model))