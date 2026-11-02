import json
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from models.moderation import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_action(
        self,
        guild_id: int,
        actor_id: int,
        action: str,
        target_entity: str,
        target_id: str,
        details: Dict[str, Any] | None = None,
    ) -> AuditLog:
        audit_entry = AuditLog(
            guild_id=guild_id,
            actor_id=actor_id,
            action=action,
            target_entity=target_entity,
            target_id=str(target_id),
            details_json=json.dumps(details or {}),
        )
        self.session.add(audit_entry)
        await self.session.flush()
        return audit_entry

