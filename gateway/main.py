from fastapi import FastAPI, Request, Response, HTTPException, Depends
from gateway.security.rate_limiter import RateLimiter 
from gateway.security.usage_logger import log_request
from contextlib import asynccontextmanager
from .logger import log_security_event
from .init_db import init_db
from .deps import get_db
import requests
import asyncio
import uuid

from gateway.ml.async_detector import schedule_behavior_analysis
from gateway.cache.window_store import record_events
from gateway.ml.model import model

# Phase 5.4 - Hybrid Decision Engine
from gateway.decision.rules import evaluate_rules
from gateway.ml.inference import infer_ml_signal
from gateway.decision.correlate import correlate_decisions
from gateway.analytics.feature_extractor import extract_features
from gateway.analytics.window_materializer import get_window_events

@asynccontextmanager
async def lifespan(app:FastAPI):
    #startup  - Code before yield → runs at startup
    init_db()
    yield
    #shutdown - Code after yield → runs at shutdown

app = FastAPI(title="API Security Gateway", lifespan=lifespan)

BACKEND_URL = "http://127.0.0.1:9000"
GATEWAY_SECRET = "gateway-internal-secret"

VALID_API_KEYS = {
    "secret123",
    "client-demo-key",
    "Testing-API-Key"
}

rate_limiter = RateLimiter(
    max_requests=10,
    window_seconds=60
)

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(request: Request, path: str, db=Depends(get_db)):
    # Step 4.4.1: Generate unique request ID
    request_id = str(uuid.uuid4())
    
    api_key = request.headers.get("X-API-KEY")
    client_ip = request.client.host if request.client else "unknown"
    
    # Validate API key first (security check)
    if api_key not in VALID_API_KEYS:
        log_security_event(
            db=db,
            client_ip=client_ip,
            api_key=api_key,
            endpoint=request.url.path,
            http_method=request.method,
            decision="BLOCK",
            reason="INVALID_API_KEY",
            status_code=401
        )
        return Response(
            content='{"detail":"Unauthorized: Invalid or missing API key"}',
            status_code=401,
            headers={"X-Request-ID": request_id}
        )
    
    # Phase 5.4 Integration - Hybrid Decision Engine
    try:
        # Get historical events for this API key
        events = get_window_events(api_key, db)
        
        # Extract behavioral features
        features = extract_features(events) if events else {}
        
        # Phase 5.4.1: Rule-based decision (ENFORCEMENT)
        rule_decision = evaluate_rules(features)
        
        # Phase 5.4.2: ML inference (OBSERVATION) 
        ml_result = {"label": None, "score": None}
        if features:
            # Convert features to ML format
            feature_vector = [
                features.get("total_requests", 0),
                features.get("requests_per_second", 0.0),
                features.get("blocked_ratio", 0.0),
                features.get("endpoints_entropy", 0.0),
                features.get("throttled_ratio", 0.0),
                0.0,  # placeholder
                0.0   # placeholder
            ]
            ml_result = infer_ml_signal(feature_vector)
        
        # Phase 5.4.3: Correlation (EXPLANATION)
        correlation = correlate_decisions(rule_decision, ml_result.get("label"))
        
        # Enforce the rule decision
        if rule_decision.value == "BLOCK":
            log_security_event(
                db=db,
                client_ip=client_ip,
                api_key=api_key,
                endpoint=request.url.path,
                http_method=request.method,
                decision="BLOCK",
                reason=f"RULE_ENGINE_BLOCK: {correlation['summary']}",
                status_code=403
            )
            return Response(
                content='{"detail":"Request blocked by security policy"}',
                status_code=403,
                headers={"X-Request-ID": request_id}
            )
        
        if rule_decision.value == "THROTTLE":
            log_security_event(
                db=db,
                client_ip=client_ip,
                api_key=api_key,
                endpoint=request.url.path,
                http_method=request.method,
                decision="THROTTLE",
                reason=f"RULE_ENGINE_THROTTLE: {correlation['summary']}",
                status_code=429
            )
            return Response(
                content='{"detail":"Request rate limited by security policy"}',
                status_code=429,
                headers={"X-Request-ID": request_id}
            )
    
    except Exception as e:
        # Fallback to safe default if Phase 5.4 fails
        print(f"Phase 5.4 error: {e}")
        rule_decision_value = "ALLOW"
        correlation = {"summary": "Phase 5.4 fallback"}
        ml_result = {"label": None, "score": None}
    
    # If we reach here, decision is ALLOW
    body = await request.body()

    # Step 4.4.1: Add gateway secret and request ID to headers forwarded to backend
    gateway_headers = dict(request.headers)
    gateway_headers["X-Gateway-Token"] = GATEWAY_SECRET
    gateway_headers["X-Request-ID"] = request_id

    backend_response = await asyncio.to_thread(
        requests.request,
        method=request.method,
        url=f"{BACKEND_URL}/{path}",
        headers=gateway_headers,
        data=body
    )
    
    # Log successful request with Phase 5.4 data
    event = log_security_event(
        db=db,
        client_ip=client_ip,
        api_key=api_key,
        endpoint=request.url.path,
        http_method=request.method,
        decision="ALLOW",
        reason=f"RULE_ENGINE_ALLOW: {correlation['summary']} | ML: {ml_result.get('label', 'N/A')}",
        status_code=backend_response.status_code
    )
    
    # Extract the event ID integer if event is an ORM object and ensure it's an int
    from sqlalchemy.sql.schema import Column

    event_id = getattr(event, "id", event)  # fallback to event if already int
    if not isinstance(event_id, int):
        # Avoid trying to cast SQLAlchemy Column objects to int
        if not isinstance(event_id, Column):
            try:
                event_id = int(event_id)
            except Exception:
                event_id = None
        else:
            event_id = None
    if event_id is not None:
        record_events(api_key, event_id)
    
    schedule_behavior_analysis(
    api_key=api_key,
    db=db,
    model=model 
    )

    # Step 4.4.1: Return response with backend headers + request ID
    return Response(
        content=backend_response.content,
        status_code=backend_response.status_code,
        headers={
            **dict(backend_response.headers),
            "X-Request-ID": request_id
        }
    )