from fastapi import FastAPI

app = FastAPI(title="数据中台", version="0.1.0")


@app.get("/")
def root():
    return {"name": "数据中台", "version": "0.1.0"}
