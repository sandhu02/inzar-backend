import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categories.models import Category


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, category_id: uuid.UUID) -> Category | None:
        result = await self.session.execute(select(Category).where(Category.id == category_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Category | None:
        result = await self.session.execute(select(Category).where(Category.slug == slug))
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Category]:
        result = await self.session.execute(
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order.asc(), Category.name.asc())
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[Category]:
        result = await self.session.execute(
            select(Category).order_by(Category.sort_order.asc(), Category.name.asc())
        )
        return list(result.scalars().all())

    async def create(self, category_data: dict[str, Any]) -> Category:
        category = Category(**category_data)
        self.session.add(category)
        await self.session.flush()
        return category

    async def update(self, category: Category, update_data: dict[str, Any]) -> Category:
        for key, value in update_data.items():
            if hasattr(category, key):
                setattr(category, key, value)
        await self.session.flush()
        return category

    async def count(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(Category))
        return result.scalar_one() or 0
