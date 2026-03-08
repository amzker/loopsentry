import asyncio
import hashlib
from pathlib import Path
from contextlib import asynccontextmanager

import aiosqlite
import aiohttp
import orjson
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loopsentry import LoopSentry


DB_PATH = Path(__file__).parent / "async_demo.db"
MOCK_BASE = "http://127.0.0.1:9999"


class SharedAiohttpSession:
    def __init__(self):
        self._session = None
        self._lock = asyncio.Lock()

    async def get_session(self):
        if self._session and not self._session.closed:
            return self._session
        async with self._lock:
            if self._session and not self._session.closed:
                return self._session
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                json_serialize=lambda x: orjson.dumps(x).decode(),
            )
            return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


class SharedAiosqlitePool:
    def __init__(self, db_path, pool_size=4):
        self._db_path = str(db_path)
        self._pool_size = pool_size
        self._pool = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._created = 0

    async def _create_conn(self):
        conn = await aiosqlite.connect(self._db_path)
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA cache_size=-8000")
        await conn.execute("PRAGMA mmap_size=67108864")
        await conn.execute("PRAGMA temp_store=MEMORY")
        conn.row_factory = aiosqlite.Row
        return conn

    async def get_conn(self):
        try:
            conn = self._pool.get_nowait()
            try:
                await conn.execute("SELECT 1")
                return conn
            except Exception:
                try:
                    await conn.close()
                except Exception:
                    pass
                self._created -= 1
        except asyncio.QueueEmpty:
            pass

        async with self._lock:
            if self._created < self._pool_size:
                self._created += 1
                try:
                    return await self._create_conn()
                except Exception:
                    self._created -= 1
                    raise

        return await self._pool.get()

    async def release(self, conn):
        await self._pool.put(conn)

    async def close(self):
        while not self._pool.empty():
            conn = self._pool.get_nowait()
            await conn.close()
        self._created = 0


http_session = SharedAiohttpSession()
db_pool = SharedAiosqlitePool(DB_PATH, pool_size=8)


async def init_db():
    conn = await db_pool.get_conn()
    try:
        await conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, email TEXT, hash TEXT)")
        await conn.execute("DELETE FROM users")
        for i in range(100):
            h = hashlib.sha256(f"user{i}".encode()).hexdigest()
            await conn.execute("INSERT INTO users (name, email, hash) VALUES (?, ?, ?)", (f"user_{i}", f"user{i}@test.com", h))
        await conn.commit()
    finally:
        await db_pool.release(conn)


def _hash_sync(password, iterations=200000):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), b"salt", iterations).hex()


def _compute_sync():
    total = 0
    for i in range(5_000_000):
        total += i * i
    return total


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    sentry = LoopSentry(
        base_dir="example_logs_async_app",
        threshold=0.1,
        async_threshold=0.5,
        capture_args=True,
        detect_async_bottlenecks=True,
    )
    sentry.start()
    yield
    sentry.stop()
    await http_session.close()
    await db_pool.close()
    DB_PATH.unlink(missing_ok=True)


app = FastAPI(title="LoopSentry Async Demo", lifespan=lifespan)


@app.get("/healthy")
async def healthy():
    return {"status": "ok"}


@app.get("/users/sync")
async def get_users():
    conn = await db_pool.get_conn()
    try:
        cursor = await conn.execute("SELECT * FROM users LIMIT 20")
        rows = await cursor.fetchall()
        return {"users": [{"id": r[0], "name": r[1], "email": r[2]} for r in rows]}
    finally:
        await db_pool.release(conn)


@app.get("/users/{user_id}")
async def get_user(user_id: int):
    conn = await db_pool.get_conn()
    try:
        cursor = await conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row:
            return JSONResponse({"error": "not found"}, 404)
        return {"id": row[0], "name": row[1], "email": row[2]}
    finally:
        await db_pool.release(conn)


@app.post("/hash")
async def hash_password(password: str = "default"):
    result = await asyncio.to_thread(_hash_sync, password)
    return {"hash": result}


@app.get("/external")
async def external_call():
    session = await http_session.get_session()
    async with session.get(f"{MOCK_BASE}/delay/1") as resp:
        data = await resp.json(content_type=None)
        return data


@app.get("/external/sync")
async def external_async():
    session = await http_session.get_session()
    try:
        async with session.get(f"{MOCK_BASE}/delay/1") as resp:
            data = await resp.json(content_type=None)
            return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, 502)


@app.get("/sleep/{seconds}")
async def async_sleep(seconds: float = 1.0):
    await asyncio.sleep(seconds)
    return {"slept": seconds}


@app.get("/compute")
async def compute_heavy():
    result = await asyncio.to_thread(_compute_sync)
    return {"result": result}


@app.get("/mixed")
async def mixed_workload():
    await asyncio.sleep(0.2)

    conn = await db_pool.get_conn()
    try:
        cursor = await conn.execute("SELECT * FROM users")
        await cursor.fetchall()
    finally:
        await db_pool.release(conn)

    await asyncio.to_thread(_hash_sync, "test", 100000)
    return {"status": "completed"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_async:app", host="0.0.0.0", port=8000, workers=2)