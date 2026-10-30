import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.modules.admin.service import AdminService
from app.modules.categories.models import Category
from app.modules.categories.repository import CategoryRepository
from app.modules.categories.schemas import CategoryCreate, CategoryUpdate

DEFAULT_CATEGORIES: list[dict[str, Any]] = [
    {
        "slug": "fire",
        "name": "Fire",
        "icon_key": "flame",
        "color_hex": "#EF4444",
        "sort_order": 1,
        "is_active": True,
        "urgency": "high",
        "default_ttl_minutes": 720,
        "stale_after_minutes": 120,
        "resolve_flag_threshold": 3,
        "notify_throttle_minutes": 30,
        "notify_by_default": True,
        "require_manual_review": False,
        "safety_note": "Keep a safe distance and do not obstruct emergency responders.",
    },
    {
        "slug": "accident",
        "name": "Traffic Accident",
        "icon_key": "car-crash",
        "color_hex": "#F97316",
        "sort_order": 2,
        "is_active": True,
        "urgency": "routine",
        "default_ttl_minutes": 360,
        "stale_after_minutes": 90,
        "resolve_flag_threshold": 3,
        "notify_throttle_minutes": 30,
        "notify_by_default": True,
        "require_manual_review": False,
        "safety_note": "Do not stop on active highways. Watch for oncoming traffic.",
    },
    {
        "slug": "road_blockage",
        "name": "Road Blockage",
        "icon_key": "barrier",
        "color_hex": "#EAB308",
        "sort_order": 3,
        "is_active": True,
        "urgency": "routine",
        "default_ttl_minutes": 720,
        "stale_after_minutes": 180,
        "resolve_flag_threshold": 3,
        "notify_throttle_minutes": 60,
        "notify_by_default": True,
        "require_manual_review": False,
        "safety_note": "Seek alternate routes if possible.",
    },
    {
        "slug": "flooding",
        "name": "Flooding",
        "icon_key": "droplets",
        "color_hex": "#3B82F6",
        "sort_order": 4,
        "is_active": True,
        "urgency": "high",
        "default_ttl_minutes": 1440,
        "stale_after_minutes": 240,
        "resolve_flag_threshold": 3,
        "notify_throttle_minutes": 30,
        "notify_by_default": True,
        "require_manual_review": False,
        "safety_note": "Do not attempt to drive or walk through flooded roadways.",
    },
    {
        "slug": "public_gathering",
        "name": "Public Gathering",
        "icon_key": "users",
        "color_hex": "#8B5CF6",
        "sort_order": 5,
        "is_active": True,
        "urgency": "routine",
        "default_ttl_minutes": 480,
        "stale_after_minutes": 180,
        "resolve_flag_threshold": 3,
        "notify_throttle_minutes": 60,
        "notify_by_default": False,
        "require_manual_review": False,
        "safety_note": "Be aware of crowds and surrounding exits.",
    },
    {
        "slug": "other_hazard",
        "name": "Other Hazard",
        "icon_key": "alert-triangle",
        "color_hex": "#6B7280",
        "sort_order": 6,
        "is_active": True,
        "urgency": "routine",
        "default_ttl_minutes": 720,
        "stale_after_minutes": 180,
        "resolve_flag_threshold": 3,
        "notify_throttle_minutes": 60,
        "notify_by_default": True,
        "require_manual_review": False,
        "safety_note": "Exercise caution and report accurate details.",
    },
]

# Simple in-memory cache for active categories
_categories_cache: list[Category] | None = None
_categories_cache_expiry: float = 0.0
CACHE_TTL_SECONDS = 60.0


def invalidate_categories_cache() -> None:
    global _categories_cache, _categories_cache_expiry
    _categories_cache = None
    _categories_cache_expiry = 0.0


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CategoryRepository(session)
        self.admin_service = AdminService(session)

    async def seed_defaults_if_needed(self) -> int:
        """Idempotently seed default categories if none exist."""
        count = await self.repo.count()
        if count > 0:
            return 0

        created = 0
        for cat_data in DEFAULT_CATEGORIES:
            existing = await self.repo.get_by_slug(cat_data["slug"])
            if not existing:
                await self.repo.create(cat_data)
                created += 1

        if created > 0:
            await self.session.commit()
            invalidate_categories_cache()
        return created

    async def list_active_categories(self) -> list[Category]:
        """List active categories ordered by sort_order and name. Uses short-lived cache."""
        global _categories_cache, _categories_cache_expiry
        now = time.monotonic()
        if _categories_cache is not None and now < _categories_cache_expiry:
            return _categories_cache

        categories = await self.repo.list_active()
        _categories_cache = categories
        _categories_cache_expiry = now + CACHE_TTL_SECONDS
        return categories

    async def list_all_categories(self) -> list[Category]:
        """Admin view: list all categories including inactive ones."""
        return await self.repo.list_all()

    async def get_category_by_id(self, category_id: uuid.UUID) -> Category:
        category = await self.repo.get_by_id(category_id)
        if not category:
            raise NotFoundError(code="category_not_found", message="Category does not exist")
        return category

    async def get_category_by_slug(self, slug: str) -> Category:
        category = await self.repo.get_by_slug(slug)
        if not category:
            raise NotFoundError(code="category_not_found", message="Category does not exist")
        return category

    async def create_category(
        self, data: CategoryCreate, actor_id: uuid.UUID | None = None
    ) -> Category:
        existing = await self.repo.get_by_slug(data.slug)
        if existing:
            raise ConflictError(
                code="category_slug_exists", message=f"Category slug '{data.slug}' already exists"
            )

        cat_dict = data.model_dump()
        category = await self.repo.create(cat_dict)

        await self.admin_service.log_audit_action(
            action="category.create",
            target_type="category",
            target_id=str(category.id),
            summary={"slug": category.slug, "name": category.name},
            actor_id=actor_id,
        )

        await self.session.commit()
        invalidate_categories_cache()
        return category

    async def update_category(
        self, category_id: uuid.UUID, data: CategoryUpdate, actor_id: uuid.UUID | None = None
    ) -> Category:
        category = await self.get_category_by_id(category_id)

        update_dict = data.model_dump(exclude_unset=True)
        if not update_dict:
            return category

        # Check cross-field validity if only one field is updated
        new_ttl = update_dict.get("default_ttl_minutes", category.default_ttl_minutes)
        new_stale = update_dict.get("stale_after_minutes", category.stale_after_minutes)
        if new_stale > new_ttl:
            raise BadRequestError(
                code="invalid_category_timing",
                message="stale_after_minutes cannot be greater than default_ttl_minutes",
            )

        before = {k: getattr(category, k) for k in update_dict}
        updated = await self.repo.update(category, update_dict)
        after = {k: getattr(updated, k) for k in update_dict}

        await self.admin_service.log_audit_action(
            action="category.update",
            target_type="category",
            target_id=str(category.id),
            summary={"before": before, "after": after},
            actor_id=actor_id,
        )

        await self.session.commit()
        invalidate_categories_cache()
        return updated
