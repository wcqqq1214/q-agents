import json
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException

from app.reporting.asset_type import classify_asset_type

from ..models import Report
from ..models.schemas import ReportTexts

router = APIRouter()

# Path to reports directory
REPORTS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "reports"


def _build_report_response(report_id: str, data: dict) -> Report:
    symbol = data.get("symbol") or "UNKNOWN"
    reports_block = data.get("reports")
    reports_payload = reports_block if isinstance(reports_block, dict) else {}
    return Report(
        id=report_id,
        symbol=symbol,
        asset_type=data.get("asset_type") or classify_asset_type(symbol),
        timestamp=data.get("timestamp", ""),
        query=data.get("query") or "",
        final_decision=data.get("final_decision"),
        quant_analysis=data.get("quant_analysis"),
        news_sentiment=data.get("news_sentiment"),
        social_sentiment=data.get("social_sentiment"),
        reports=ReportTexts(**reports_payload),
    )


@router.get("/reports", response_model=List[Report])
async def get_reports():
    """Get all available reports."""
    if not REPORTS_DIR.exists():
        return []

    reports = []
    for report_dir in sorted(REPORTS_DIR.iterdir(), reverse=True):
        if not report_dir.is_dir():
            continue

        # Look for report.json in the directory
        report_file = report_dir / "report.json"
        if not report_file.exists():
            continue

        try:
            with open(report_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                reports.append(_build_report_response(report_dir.name, data))
        except Exception:
            # Skip invalid reports
            continue

    return reports


@router.get("/reports/{report_id}", response_model=Report)
async def get_report(report_id: str):
    """Get a specific report by ID."""
    report_dir = REPORTS_DIR / report_id
    if not report_dir.exists():
        raise HTTPException(status_code=404, detail="Report not found")

    report_file = report_dir / "report.json"
    if not report_file.exists():
        raise HTTPException(status_code=404, detail="Report file not found")

    try:
        with open(report_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return _build_report_response(report_id, data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading report: {str(e)}") from e
