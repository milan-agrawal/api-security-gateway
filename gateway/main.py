from fastapi import FastAPI, Request, Response, HTTPException
import requests
import asyncio

app = FastAPI(title="API Security Gateway")

BACKEND_URL = "http://127.0.0.1:9000"

VALID_API_KEYS = {
    "secret123",
    "client-demo-key",
    "Testing-API-Key"
}

@app.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy(request: Request, path: str):

    api_key=request.headers.get("X-API-KEY")
    if api_key not in VALID_API_KEYS:
            raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing API key"
        )
    body = await request.body()   # ✅ await the coroutine

    backend_response = await asyncio.to_thread(
        requests.request,
        method=request.method,
        url=f"{BACKEND_URL}/{path}",
        headers=dict(request.headers),
        data=body
    )

    return Response(
        content=backend_response.content,
        status_code=backend_response.status_code,
        headers=dict(backend_response.headers)
    )