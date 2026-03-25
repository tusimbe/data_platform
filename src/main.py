from fastapi import FastAPI
from src.api.health import router as health_router

app = FastAPI(title="数据中台", version="0.1.0")

app.include_router(health_router, prefix="/api/v1")


@app.get("/")
def root():
    return {"name": "数据中台", "version": "0.1.0"}
