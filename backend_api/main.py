from fastapi import FastAPI,Header,HTTPException

app = FastAPI(title="Protected Backend API")

GATEWAY_SECRET = "gateway-internal-secret"

@app.get("/api/data")
def get_data(x_gateway_token: str = Header(None)):
    if x_gateway_token != GATEWAY_SECRET:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Direct access to backend is not allowed"
        )

    return {"message": "the Data is Protected behind the API Gateway"}