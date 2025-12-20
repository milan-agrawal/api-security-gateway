from fastapi import FastAPI

app = FastAPI(title="Protected Backend API")

@app.get("/api/data")
def get_data():
    return{ "message": "the Data is Protected behind the API Gateway"}

