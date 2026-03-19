from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from app.tasks.update_ohlc import update_daily_ohlc

from .models import HealthResponse
from .routes import analyze, reports, system, settings, stocks, ohlc

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Finance Agent API",
    description="Multi-agent financial analysis system API",
    version="0.1.0",
)

# Create scheduler
scheduler = BackgroundScheduler()


@app.on_event("startup")
def start_scheduler():
    """Start scheduled tasks on app startup."""
    # Update daily after US market close (UTC 21:30 = EST 16:30)
    scheduler.add_job(
        update_daily_ohlc,
        'cron',
        hour=21,
        minute=30,
        id='daily_ohlc_update'
    )
    scheduler.start()
    logger.info("✓ Scheduler started: daily OHLC update at 21:30 UTC")


@app.on_event("shutdown")
def shutdown_scheduler():
    """Shutdown scheduler on app shutdown."""
    scheduler.shutdown()
    logger.info("✓ Scheduler stopped")


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000",],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(analyze.router, prefix="/api", tags=["analyze"])
app.include_router(reports.router, prefix="/api", tags=["reports"])
app.include_router(system.router, prefix="/api", tags=["system"])
app.include_router(settings.router, prefix="/api", tags=["settings"])
app.include_router(stocks.router, prefix="/api", tags=["stocks"])
app.include_router(ohlc.router, prefix="/api/stocks", tags=["ohlc"])


@app.get("/")
async def root():
    return {"message": "Finance Agent API", "version": "0.1.0"}


@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
    )
