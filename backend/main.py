from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.scheduler_service import start_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the background scheduler on boot (no-op unless SCHEDULER_ENABLED).
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="Fantas.ai", version="0.1.0", lifespan=lifespan)

# Allow requests from the React frontend (Vercel + local dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routers import roster, projections, settings, news, tracker, startsit, admin
app.include_router(roster.router, prefix="/api")
app.include_router(projections.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(tracker.router, prefix="/api")
app.include_router(startsit.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "Fantas.ai"}
