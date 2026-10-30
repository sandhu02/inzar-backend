import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.dependencies import require_admin
from app.modules.categories.schemas import (
    CategoryCreate,
    CategoryPublicResponse,
    CategoryResponse,
    CategoryUpdate,
)
from app.modules.categories.service import CategoryService
from app.modules.users.models import User

router = APIRouter(tags=["Categories"])
admin_categories_router = APIRouter(prefix="/admin/categories", tags=["Admin - Categories"])


# Public route
@router.get(
    "/categories",
    response_model=list[CategoryPublicResponse],
    summary="Get active categories for reporting and filters",
)
async def get_active_categories(
    db: AsyncSession = Depends(get_db),
) -> list[CategoryPublicResponse]:
    service = CategoryService(db)
    categories = await service.list_active_categories()
    return [CategoryPublicResponse.model_validate(c) for c in categories]


# Admin routes
@admin_categories_router.get(
    "",
    response_model=list[CategoryResponse],
    summary="List all categories including inactive ones",
)
async def list_all_categories_admin(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[CategoryResponse]:
    service = CategoryService(db)
    categories = await service.list_all_categories()
    return [CategoryResponse.model_validate(c) for c in categories]


@admin_categories_router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new incident category",
)
async def create_category_admin(
    payload: CategoryCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> CategoryResponse:
    service = CategoryService(db)
    category = await service.create_category(payload, actor_id=admin.id)
    return CategoryResponse.model_validate(category)


@admin_categories_router.patch(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Update category configuration and tunables",
)
async def update_category_admin(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> CategoryResponse:
    service = CategoryService(db)
    category = await service.update_category(category_id, payload, actor_id=admin.id)
    return CategoryResponse.model_validate(category)
