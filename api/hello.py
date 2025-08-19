# api/hello.py
from fastapi import FastAPI

app = FastAPI()

@app.get("/api/hello")
def hello():
    return {"ok": True, "runtime": "python3.11"}
