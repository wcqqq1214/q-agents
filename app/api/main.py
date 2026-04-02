import asyncio
import inspect
import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from arq import create_pool
from arq.connections import RedisSettings
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config_manager import config_manager
from app.database.agent_history import init_db as init_agent_history_db
from app.database.crypto_ohlc import get_max_date
from app.mcp_client.connection_manager import get_mcp_connection_manager
from app.services.batch_downloader import download_daily_data
from app.services.realtime_agent import update_hot_cache_loop, warmup_hot_cache
from app.services.stock_updater import update_stocks_intraday
from app.tasks.update_ohlc import update_daily_ohlc

from .models import HealthResponse
from .routes import (
    analyze,
    crypto,
    crypto_klines,
    history,
    ohlc,
    okx,
    reports,
    settings,
    stocks,
    system,
)

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Create scheduler
scheduler = AsyncIOScheduler(timezone="America/New_York")

# Symbols and intervals for batch downloads
CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
CRYPTO_INTERVALS = ["1m", "1d"]


async def create_arq_pool():
    """Create the shared ARQ pool when Redis is enabled."""
    redis_settings = config_manager.get_redis_settings()
    if not redis_settings["redis_enabled"]:
        logger.info("Redis disabled, skipping ARQ pool initialization")
        return None

    try:
        pool = await create_pool(RedisSettings.from_dsn(redis_settings["redis_url"]))
        await pool.ping()
        logger.info("✓ ARQ pool initialized")
        return pool
    except Exception as exc:
        logger.warning(
            "Failed to initialize ARQ pool, background jobs will fall back to local execution: %s",
            exc,
        )
        return None


async def close_arq_pool(pool) -> None:
    """Close the shared ARQ pool if present."""
    if pool is None:
        return

    close_result = pool.aclose()
    if inspect.isawaitable(close_result):
        await close_result


async def enqueue_daily_ohlc_job(app: FastAPI) -> None:
    """Enqueue the OHLC update job or fall back to local execution."""
    arq_pool = getattr(app.state, "arq_pool", None)
    if arq_pool is not None:
        await arq_pool.enqueue_job("update_daily_ohlc")
        logger.info("Enqueued daily OHLC update task to ARQ")
        return

    logger.warning("ARQ pool unavailable, running daily OHLC update in-process")
    await update_daily_ohlc()


def daily_crypto_download():
    """Download yesterday's crypto data from Binance Vision with catch-up mechanism."""
    logger.info("Starting daily crypto data download...")
    yesterday = date.today() - timedelta(days=1)

    # Track statistics
    total_downloads = 0
    successful_downloads = 0
    failed_downloads = 0

    for symbol in CRYPTO_SYMBOLS:
        for interval in CRYPTO_INTERVALS:
            try:
                # Get the maximum date in database for this symbol/interval
                max_date = get_max_date(symbol, interval)

                # Determine dates to download
                if max_date is None:
                    # No data exists, download only yesterday
                    logger.info(
                        f"No data in database for {symbol} {interval}, downloading yesterday only"
                    )
                    dates_to_download = [yesterday]
                elif max_date >= yesterday:
                    # Data is current, no download needed
                    logger.info(
                        f"Database up to date for {symbol} {interval} (max date: {max_date})"
                    )
                    dates_to_download = []
                else:
                    # Calculate missing dates (from day after max_date to yesterday)
                    dates_to_download = []
                    current_date = max_date + timedelta(days=1)
                    while current_date <= yesterday:
                        dates_to_download.append(current_date)
                        current_date += timedelta(days=1)
                    logger.info(
                        f"Found {len(dates_to_download)} missing dates for {symbol} {interval}: {dates_to_download[0]} to {dates_to_download[-1]}"
                    )

                # Download each missing date
                for target_date in dates_to_download:
                    total_downloads += 1
                    try:
                        # Run async function in sync context
                        asyncio.run(download_daily_data(symbol, interval, target_date))
                        successful_downloads += 1
                        logger.info(f"✓ Downloaded {symbol} {interval} for {target_date}")
                    except Exception as e:
                        failed_downloads += 1
                        logger.error(
                            f"✗ Failed to download {symbol} {interval} for {target_date}: {e}"
                        )

            except Exception as e:
                logger.error(f"Failed to process {symbol} {interval}: {e}")

    logger.info(
        f"Daily crypto data download completed: "
        f"total={total_downloads}, successful={successful_downloads}, failed={failed_downloads}"
    )


async def background_cache_warmup():
    """Background task for hot cache warmup with error handling."""
    try:
        logger.info("Starting hot cache warmup in background...")
        await warmup_hot_cache()
        logger.info("✓ Hot cache warmup completed successfully")
    except Exception as exc:
        logger.error(f"✗ Hot cache warmup failed: {exc}", exc_info=True)


async def background_stock_catchup():
    """Background task for stock data catch-up on startup."""
    from app.config_manager import get_stock_catchup_config
    from app.services.stock_updater import catchup_historical_stocks

    try:
        config = get_stock_catchup_config()
        if not config["enabled"]:
            logger.info("Stock catchup disabled by config")
            return

        logger.info(f"Starting stock catchup (max {config['catchup_days']} days)...")
        stats = await catchup_historical_stocks(days=config["catchup_days"])

        if stats["symbols_updated"] > 0:
            logger.info(
                f"✓ Stock catchup completed: {stats['symbols_updated']} symbols, "
                f"{stats['records_added']} records, range: {stats['date_range']}"
            )

        if stats["errors"]:
            logger.warning(f"Catchup errors: {stats['errors']}")

    except Exception as exc:
        logger.error(f"✗ Stock catchup failed: {exc}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("Starting Finance Agent API...")
    mcp_manager = get_mcp_connection_manager()
    app.state.mcp_connection_manager = mcp_manager

    # Prewarm Redis connection pool before any concurrent operations
    from app.services.redis_client import get_redis_client, ping_redis

    try:
        client = await get_redis_client()
        if client is not None:
            await ping_redis()
            logger.info("✓ Redis connection pool prewarmed")
    except Exception as exc:
        logger.warning(f"Redis prewarm failed (will use fallback): {exc}")

    app.state.arq_pool = await create_arq_pool()

    try:
        await mcp_manager.ensure_all_started()
        logger.info("✓ MCP servers loaded from %s", mcp_manager.config_path)
    except Exception as exc:
        logger.warning("MCP bootstrap failed, lazy reconnect will be used: %s", exc)

    # Initialize agent history database
    db_path = os.getenv("AGENT_HISTORY_DB_PATH", "data/agent_history.db")
    init_agent_history_db(db_path)
    logger.info(f"✓ Agent history database initialized: {db_path}")

    # Start hot cache warmup as non-blocking background task
    warmup_task = asyncio.create_task(background_cache_warmup())
    logger.info("✓ Hot cache warmup started in background (non-blocking)")

    # Start hot cache update loop as background task
    update_task = asyncio.create_task(update_hot_cache_loop())
    logger.info("✓ Hot cache update loop started")

    # Start stock catchup as non-blocking background task
    catchup_task = asyncio.create_task(background_stock_catchup())
    logger.info("✓ Stock catchup started in background (non-blocking)")

    # Schedule daily crypto data download at 08:00 UTC
    scheduler.add_job(daily_crypto_download, "cron", hour=8, minute=0, id="daily_crypto_download")
    logger.info("✓ Scheduled daily crypto download at 08:00 UTC")

    # Update daily after US market close (UTC 21:30 = EST 16:30)
    scheduler.add_job(
        enqueue_daily_ohlc_job,
        "cron",
        hour=21,
        minute=30,
        args=[app],
        id="daily_ohlc_update",
    )

    logger.info("Configuring intraday stock update scheduler...")
    scheduler.add_job(
        update_stocks_intraday,
        trigger=CronTrigger(minute="1,16,31,46", timezone="America/New_York"),
        id="intraday_stock_update",
        name="Intraday Stock Data Update (15min)",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("✓ Intraday stock update configured: updates at :01, :16, :31, :46 (ET)")

    scheduler.start()
    logger.info("✓ APScheduler started: updates at :01, :16, :31, :46 (ET)")

    yield

    # Shutdown
    logger.info("Shutting down Finance Agent API...")

    # Cancel warmup task if still running
    if not warmup_task.done():
        logger.info("Cancelling hot cache warmup task...")
        warmup_task.cancel()
        try:
            await warmup_task
        except asyncio.CancelledError:
            logger.info("✓ Hot cache warmup task cancelled")

    # Cancel update loop task
    update_task.cancel()
    try:
        await update_task
    except asyncio.CancelledError:
        pass

    # Cancel catchup task if still running
    if not catchup_task.done():
        logger.info("Cancelling stock catchup task...")
        catchup_task.cancel()
        try:
            await catchup_task
        except asyncio.CancelledError:
            logger.info("✓ Stock catchup task cancelled")

    scheduler.shutdown()
    await mcp_manager.shutdown_managed_servers()
    await close_arq_pool(getattr(app.state, "arq_pool", None))
    logger.info("✓ Scheduler stopped")


app = FastAPI(
    title="Finance Agent API",
    description="Multi-agent financial analysis system API",
    version="0.1.0",
    lifespan=lifespan,
)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
    ],
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
app.include_router(history.router, prefix="/api", tags=["history"])
app.include_router(okx.router, prefix="/api", tags=["okx"])
app.include_router(crypto.router, prefix="/api/crypto", tags=["crypto"])
app.include_router(crypto_klines.router, prefix="/api", tags=["crypto-klines"])


@app.get("/")
async def root():
    return {"message": "Finance Agent API", "version": "0.1.0"}


@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
    )
