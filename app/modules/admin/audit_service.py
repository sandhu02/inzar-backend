import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.models import AuditLog
from app.modules.admin.repository import AdminRepository


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AdminRepository(session)

    async def log_audit_action(
        self,
        action: str,
        target_type: str,
        target_id: str | None = None,
        summary: dict[str, Any] | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> AuditLog:
        return await self.repo.create_audit_log(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            summary=summary or {},
        )

    async def get_audit_logs(
        self,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
        target_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        return await self.repo.list_audit_logs(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            limit=limit,
            offset=offset,
        )

