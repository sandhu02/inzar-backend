from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.dependencies import require_admin
from app.modules.settings.schemas import (
    GlobalSettingsSchema,
    GlobalSettingsUpdateSchema,
    PublicConfigResponse,
)
from app.modules.settings.service import SettingsService
from app.modules.users.models import User

router = APIRouter(tags=["Config"])
admin_settings_router = APIRouter(prefix="/admin/settings", tags=["Admin - Settings"])


@router.get(
    "/config",
    response_model=PublicConfigResponse,
    summary="Get public application configuration and map constraints",
)
async def get_public_config(
    db: AsyncSession = Depends(get_db),
) -> PublicConfigResponse:
    service = SettingsService(db)
    return await service.get_public_config()


@admin_settings_router.get(
    "",
    response_model=GlobalSettingsSchema,
    summary="Get all global admin-tunable settings",
)
async def get_admin_settings(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> GlobalSettingsSchema:
    service = SettingsService(db)
    return await service.get_global_settings()


@admin_settings_router.patch(
    "",
    response_model=GlobalSettingsSchema,
    summary="Update global admin-tunable settings",
)
async def update_admin_settings(
    payload: GlobalSettingsUpdateSchema,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> GlobalSettingsSchema:
    service = SettingsService(db)
    return await service.update_global_settings(payload, actor_id=admin.id)
