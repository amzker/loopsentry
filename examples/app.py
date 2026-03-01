import asyncio
import time
import hashlib
import json
import sqlite3
from pathlib import Path
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loopsentry import LoopSentry


DB_PATH = Path(__file__).parent / "demo.db"


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, email TEXT, hash TEXT)")
    conn.execute("DELETE FROM users")
    for i in range(100):
        h = hashlib.sha256(f"user{i}".encode()).hexdigest()
        conn.execute("INSERT INTO users (name, email, hash) VALUES (?, ?, ?)", (f"user_{i}", f"user{i}@test.com", h))
    conn.commit()
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    sentry = LoopSentry(
        base_dir="example_logs",
        threshold=0.05,
        async_threshold=0.5,
        capture_args=True,
        detect_async_bottlenecks=True,
    )
    sentry.start()
    yield
    DB_PATH.unlink(missing_ok=True)


app = FastAPI(title="LoopSentry Demo API", lifespan=lifespan)


@app.get("/healthy")
async def healthy():
    return {"status": "ok"}


@app.get("/users/sync")
async def get_users_sync():
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("SELECT * FROM users LIMIT 20").fetchall()
    conn.close()
    return {"users": [{"id": r[0], "name": r[1], "email": r[2]} for r in rows]}


@app.get("/users/{user_id}")
async def get_user(user_id: int):
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return JSONResponse({"error": "not found"}, 404)
    return {"id": row[0], "name": row[1], "email": row[2]}


@app.post("/hash")
async def hash_password(password: str = "default"):
    result = hashlib.pbkdf2_hmac("sha256", password.encode(), b"salt", 200000)
    return {"hash": result.hex()}


@app.get("/external")
async def external_call():
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://httpbin.org/delay/1")
        return resp.json()


@app.get("/external/sync")
async def external_sync():
    import requests
    resp = requests.get("https://httpbin.org/delay/1")
    return resp.json()


@app.get("/sleep/{seconds}")
async def blocking_sleep(seconds: float = 1.0):
    time.sleep(seconds)
    return {"slept": seconds}


@app.get("/compute")
async def compute_heavy():
    total = 0
    for i in range(5_000_000):
        total += i * i
    return {"result": total}


@app.get("/mixed")
async def mixed_workload():
    time.sleep(0.2)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("SELECT * FROM users").fetchall()
    conn.close()

    hashlib.pbkdf2_hmac("sha256", b"test", b"salt", 100000)

    return {"status": "completed"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, workers=2)