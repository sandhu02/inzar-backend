from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
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
