import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Uvicorn only configures its own loggers, so without this every logger.info/warning/error
# in services/ and routers/ is dropped: no scheduler, scraper or Gemini output anywhere.
# Uvicorn's own loggers don't propagate to root, so nothing is logged twice.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from config import ALLOWED_ORIGINS, ESPN_COOKIE_KEY
from services.scheduler_service import start_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Without the key, stored ESPN cookies read as "disconnected" and saving new ones
    # fails, which would otherwise surface as a confusing ESPN problem, not a config one.
    if not ESPN_COOKIE_KEY:
        logging.getLogger(__name__).error("ESPN_COOKIE_KEY is not set: ESPN leagues cannot connect or sync.")
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

# Sent on everything. HSTS is ignored over plain http, so it only takes effect on the real
# https host; the rest stop MIME sniffing, framing, referrer leaks and unused browser APIs.
SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}
# Only for /api: it returns JSON and never needs to load anything. /docs is exempt because
# Swagger UI pulls its scripts from a CDN. no-store keeps one user's roster out of any cache.
API_ONLY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
}


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    if request.url.path.startswith("/api/"):
        response.headers.update(API_ONLY_HEADERS)
    return response

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
