from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.alerts.schemas import (
    AlertPreferencesResponse,
    AlertPreferencesUpdate,
    DeviceTokenCreate,
    DeviceTokenResponse,
)
from app.modules.alerts.service import AlertService
from app.modules.auth.dependencies import require_user
from app.modules.users.models import User

router = APIRouter(prefix="/me", tags=["Me - Alerts & Devices"])


@router.get(
    "/alert-preferences",
    response_model=AlertPreferencesResponse,
    summary="Get user alert preferences and spatial notification radius",
)
async def get_alert_preferences(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> AlertPreferencesResponse:
    service = AlertService(db)
    return await service.get_preferences(current_user)


@router.put(
    "/alert-preferences",
    response_model=AlertPreferencesResponse,
    summary="Update user alert center, radius, categories, and urgency thresholds",
)
async def update_alert_preferences(
    payload: AlertPreferencesUpdate,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> AlertPreferencesResponse:
    service = AlertService(db)
    return await service.update_preferences(current_user, payload)


@router.post(
    "/devices",
    response_model=DeviceTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a push notification device token",
)
async def register_device(
    payload: DeviceTokenCreate,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceTokenResponse:
    service = AlertService(db)
    return await service.register_device(current_user, payload)


@router.delete(
    "/devices/{token}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unregister a device token",
)
async def unregister_device(
    token: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = AlertService(db)
    await service.unregister_device(current_user, token)
