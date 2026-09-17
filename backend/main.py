from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Fantas.ai", version="0.1.0")

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
