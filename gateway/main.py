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
    
    allowed = rate_limiter.allow_request(api_key)
    log_request(api_key=api_key, endpoint=request.url.path, allowed=allowed)
    
    if not allowed:
        # Log security event for rate limit
        log_security_event(
            db=db,
            client_ip=request.client.host if request.client else "unknown",
            api_key=api_key,
            endpoint=request.url.path,
            http_method=request.method,
            decision="THROTTLE",
            reason="RATE_LIMIT_EXCEEDED",
            status_code=429
        )
        return Response(
            content="Rate limit exceeded",
            status_code=429,
            headers={"X-Request-ID": request_id}
        )
    
    if api_key not in VALID_API_KEYS:
        # Log security event for invalid API key
        log_security_event(
            db=db,
            client_ip=request.client.host if request.client else "unknown",
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
    
    # Log successful request
    log_security_event(
        db=db,
        client_ip=request.client.host if request.client else "unknown",
        api_key=api_key,
        endpoint=request.url.path,
        http_method=request.method,
        decision="ALLOW",
        reason="OK",
        status_code=backend_response.status_code
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