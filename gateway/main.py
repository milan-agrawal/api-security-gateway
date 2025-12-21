from fastapi import FastAPI, Request, Response, HTTPException, Depends
from gateway.security.rate_limiter import RateLimiter 
from gateway.security.usage_logger import log_request
from contextlib import asynccontextmanager
from .logger import log_security_event
from .init_db import init_db
from .deps import get_db
import requests
import asyncio

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

    api_key=request.headers.get("X-API-KEY")
    
    allowed = rate_limiter.allow_request(api_key)
    log_request(api_key = api_key, endpoint=request.url.path, allowed = allowed)
    
    if not allowed:
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
            status_code=429
        )
    
    if api_key not in VALID_API_KEYS:

        log_security_event(
            db=db,
            client_ip=request.client.host if request.client else "unknown",
            api_key=api_key,
            endpoint=request.url.path,
            http_method=request.method,
            decision="BLOCKED",
            reason="INVALID_API_KEY",
            status_code=401
        )

        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing API key"
        )
            
    body = await request.body()   # await the coroutine

    # Add gateway secret header for backend security
    gateway_headers = dict(request.headers)
    gateway_headers["X-Gateway-Token"] = GATEWAY_SECRET

    backend_response = await asyncio.to_thread(
        requests.request,
        method=request.method,
        url=f"{BACKEND_URL}/{path}",
        headers=gateway_headers,  # Use modified headers with secret for backend LockDown
        data=body
    )
    
    log_security_event(
        db=db,
        client_ip=request.client.host if request.client else "unknown",
        api_key=api_key,
        endpoint=request.url.path,
        http_method=request.method,
        decision="ALLOWED",
        reason="OK",
        status_code=backend_response.status_code,
    )
    
    return Response(
        content=backend_response.content,
        status_code=backend_response.status_code,
        headers=dict(backend_response.headers)
    )