from fastapi import APIRouter

from app.modules.admin.router import admin_router
from app.modules.alerts.router import router as alerts_router
from app.modules.auth.router import router as auth_router
from app.modules.categories.router import admin_categories_router
from app.modules.categories.router import router as categories_router
from app.modules.incidents.router import me_incidents_router
from app.modules.incidents.router import router as incidents_router
from app.modules.settings.router import admin_settings_router
from app.modules.settings.router import router as settings_router
from app.modules.users.router import router as users_router

api_v1_router = APIRouter(prefix="/api/v1")


@api_v1_router.get("/info", tags=["System"])
async def api_info() -> dict[str, str]:
    return {
        "name": "Inzar API",
        "version": "v1",
        "status": "operational",
    }


# Mount module routers
api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(categories_router)
api_v1_router.include_router(admin_categories_router)
api_v1_router.include_router(settings_router)
api_v1_router.include_router(admin_settings_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(incidents_router)
api_v1_router.include_router(me_incidents_router)
api_v1_router.include_router(alerts_router)
