from fastapi import FastAPI, Header, HTTPException, Depends, Request
from contextlib import asynccontextmanager
from gateway.init_db import init_db  # Reuse gateway's init_db
from gateway.deps import get_db      # Reuse gateway's database dependency
from backend_api.models import BackendEvent  # Step 4.4.4: For logging backend events
import time  # Step 4.4.3: For latency measurement

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - Initialize database (creates both gateway and backend tables)
    init_db()
    yield
    # Shutdown

app = FastAPI(title="Protected Backend API", lifespan=lifespan)

GATEWAY_SECRET = "gateway-internal-secret"

@app.get("/api/data")
def get_data(request: Request, x_gateway_token: str = Header(None), db=Depends(get_db)):
    # Step 4.4.3: Start latency measurement
    start_time = time.time()
    
    if x_gateway_token != GATEWAY_SECRET:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Direct access to backend is not allowed"
        )

    # Process the request (main business logic)
    response_data = {"message": "the Data is Protected behind the API Gateway"}
    
    # Step 4.4.3: Calculate latency after processing
    latency_ms = int((time.time() - start_time) * 1000)
    
    # Step 4.4.4: Log backend event
    event = BackendEvent(
        request_id=request.headers.get("X-Request-ID"),
        endpoint=request.url.path,
        method=request.method,
        status_code=200,  # Success status code
        latency_ms=latency_ms
    )
    db.add(event)
    db.commit()
    
    return response_data