from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import async_session_factory
from core.permissions import get_current_user_claims, require_permission, require_role

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

__all__ = [
    "get_db_session",
    "get_current_user_claims",
    "require_role",
    "require_permission",
]

