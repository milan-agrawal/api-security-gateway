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

# 2️⃣ Centralized Decision Logging Function
def log_and_respond(
    *,
    db,
    request_id: str,
    client_ip: str,
    api_key: str,
    endpoint: str,
    method: str,
    decision: str,
    reason: str,
    status_code: int,
    content: str = ""
):
    """
    Centralized logging and response function - ensures:
    - One log per request
    - One response per request  
    - One decision per request
    """
    log_security_event(
        db=db,
        client_ip=client_ip,
        api_key=api_key,
        endpoint=endpoint,
        http_method=method,
        decision=decision,
        reason=reason,
        status_code=status_code
    )

    return Response(
        content=content,
        status_code=status_code,
        headers={"X-Request-ID": request_id}
    )
    
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(request: Request, path: str, db=Depends(get_db)):

    # Generate unique request ID
    request_id = str(uuid.uuid4())
    
    api_key=request.headers.get("X-API-KEY")
    
    allowed = rate_limiter.allow_request(api_key)
    log_request(api_key = api_key, endpoint=request.url.path, allowed = allowed)
    
    if not allowed:
        return log_and_respond(
            db=db,
            request_id=request_id,
            client_ip=request.client.host if request.client else "unknown",
            api_key=api_key,
            endpoint=request.url.path,
            method=request.method,
            decision="THROTTLE",
            reason="RATE_LIMIT_EXCEEDED",
            status_code=429,
            content="Rate limit exceeded"
        )
    
    if api_key not in VALID_API_KEYS:
        return log_and_respond(
            db=db,
            request_id=request_id,
            client_ip=request.client.host if request.client else "unknown",
            api_key=api_key,
            endpoint=request.url.path,
            method=request.method,
            decision="BLOCK",
            reason="INVALID_API_KEY",
            status_code=401,
            content='{"detail":"Unauthorized: Invalid or missing API key"}'
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
    
    return log_and_respond(
        db=db,
        request_id=request_id,
        client_ip=request.client.host if request.client else "unknown",
        api_key=api_key,
        endpoint=request.url.path,
        method=request.method,
        decision="ALLOW",
        reason="OK",
        status_code=backend_response.status_code,
        content=backend_response.content.decode('utf-8') if isinstance(backend_response.content, bytes) else backend_response.content
    )