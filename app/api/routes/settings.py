"""Settings API routes."""

from fastapi import APIRouter, HTTPException

from app.api.models import SettingsRequest, SettingsResponse
from app.config_manager import config_manager

router = APIRouter()


@router.get("/settings", response_model=SettingsResponse)
async def get_settings():
    """Get current settings with masked API keys.

    Returns:
        SettingsResponse: Current settings with masked keys
    """
    try:
        settings = config_manager.get_settings()
        return SettingsResponse(**settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get settings: {str(e)}")


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(request: SettingsRequest):
    """Update settings.

    Args:
        request: Settings to update

    Returns:
        SettingsResponse: Updated settings with masked keys
    """
    try:
        updates = request.model_dump(exclude_none=True)
        settings = config_manager.update_settings(updates)
        return SettingsResponse(**settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")
