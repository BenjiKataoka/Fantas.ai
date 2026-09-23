from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGINS
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
    allow_origins=ALLOWED_ORIGINS,  # exact origins; "*.vercel.app" never matched
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routers import roster, projections, settings, news, tracker, startsit, admin, recap, waivers, portfolio, matchups, results, tape
app.include_router(recap.router, prefix="/api")
app.include_router(waivers.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(matchups.router, prefix="/api")
app.include_router(results.router, prefix="/api")
app.include_router(tape.router, prefix="/api")
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
