import os
import sys
import math
import time
import asyncio
import asyncpg
import json
import redis.asyncio as redis
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator

try:
    REDIS = os.environ["REDIS"]
    DB_HOST = os.environ["DB_HOST"]
    DB_NAME = os.environ["DB_NAME"]
    DB_USER = os.environ["DB_USER"]
    DB_PASSWORD = os.environ["DB_PASSWORD"]
except KeyError as e:
    sys.exit(f"Missing environment variable: {e}")


class ScoreInput(BaseModel):
    player: str
    score: int


pg = None
rd = None
CACHE_KEY = "leaderboard:top10"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pg, rd
    pg = await asyncpg.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )
    await pg.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id SERIAL PRIMARY KEY,
            player VARCHAR(50),
            score INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    rd = await redis.from_url(f"redis://{REDIS}:6379")
    yield
    await pg.close()
    await rd.close()


app = FastAPI(lifespan=lifespan)

Instrumentator().instrument(app).expose(app)

app.mount("/public", StaticFiles(directory="public"), name="public")


@app.get("/")
async def root():
    return FileResponse("public/index.html")


@app.post("/scores")
async def submit_score(body: ScoreInput):
    await pg.execute(
        "INSERT INTO scores (player, score) VALUES ($1, $2)", body.player, body.score
    )
    await rd.delete(CACHE_KEY)
    return {"ok": True}


@app.get("/scores")
async def get_scores():
    cached = await rd.get(CACHE_KEY)
    if cached:
        return json.loads(cached)
    rows = await pg.fetch(
        "SELECT player, score FROM scores ORDER BY score DESC LIMIT 10"
    )
    scores = [dict(row) for row in rows]
    await rd.set(CACHE_KEY, __import__("json").dumps(scores), ex=30)
    return scores


@app.get("/healthz")
async def liveness():
    return {"status": "ok"}


@app.get("/ready")
async def readiness(response: Response):
    try:
        await pg.fetchval("SELECT 1")
        await rd.ping()
        return {"status": "ready"}
    except Exception as e:
        response.status_code = 503
        return {"status": "not ready", "reason": str(e)}


@app.post("/kill")
async def kill():
    os.kill(os.getpid(), 9)


@app.post("/chaos/flood-cache")
async def flood_cache():
    payload = "x" * 1_000_000
    for i in range(10_000):
        await rd.set(f"flood:{i}", payload)
    return {"flooded": True}


@app.post("/chaos/clear-cache")
async def clear_cache():
    await rd.flushall()
    return {"cleared": True}


@app.get("/stress/cpu")
def stress_cpu(duration: int = 30):
    end = time.time() + duration
    iterations = 0
    while time.time() < end:
        math.sqrt(123456789) * math.factorial(50)
        iterations += 1
    return {"status": "done", "duration_seconds": duration, "iterations": iterations}


@app.get("/stress/memory")
async def stress_memory(mb: int = 100, duration: int = 30):
    data = bytearray(mb * 1024 * 1024)
    await asyncio.sleep(duration)
    del data
    return {"status": "done", "allocated_mb": mb, "duration_seconds": duration}
