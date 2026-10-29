from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.dependencies import require_user
from app.modules.users.models import User
from app.modules.users.schemas import UserExportData, UserResponse, UserUpdate
from app.modules.users.service import UserService

router = APIRouter(prefix="/me", tags=["Me"])


def get_user_service(session: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(session)


@router.get(
    "",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_my_profile(
    current_user: User = Depends(require_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    return await user_service.get_profile(current_user.id)


@router.patch(
    "",
    response_model=UserResponse,
    summary="Update current user profile",
)
async def update_my_profile(
    payload: UserUpdate,
    current_user: User = Depends(require_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    return await user_service.update_profile(current_user.id, payload)


@router.delete(
    "",
    status_code=200,
    summary="Delete current user account",
)
async def delete_my_account(
    current_user: User = Depends(require_user),
    user_service: UserService = Depends(get_user_service),
) -> dict[str, str]:
    await user_service.delete_account(current_user.id)
    return {"message": "Account successfully deleted"}


@router.get(
    "/export",
    response_model=UserExportData,
    summary="Export all personal account data",
)
async def export_my_data(
    current_user: User = Depends(require_user),
    user_service: UserService = Depends(get_user_service),
) -> UserExportData:
    return await user_service.export_data(current_user.id)
