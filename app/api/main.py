from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from .models import HealthResponse
from .routes import analyze, reports, system, settings, stocks, ohlc

app = FastAPI(
    title="Finance Agent API",
    description="Multi-agent financial analysis system API",
    version="0.1.0",
)

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
