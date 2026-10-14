"""FastAPI application entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .realtime.manager import manager
from .routers import auth, boards, comments, tasks, ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Hackathon shortcut: create tables on boot (use Alembic for real migrations).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await manager.start(settings.redis_url)
    yield
    await manager.stop()
    await engine.dispose()


app = FastAPI(title="Realtime Kanban API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],  # includes X-Client-ID
)

for r in (auth.router, boards.router, tasks.router, comments.router):
    app.include_router(r, prefix="/api")
app.include_router(ws.router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "ws_connections": manager.connection_count}
