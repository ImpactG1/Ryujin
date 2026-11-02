from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from core.config import settings
from core.logger import logger


class Base(DeclarativeBase):
    pass


def create_engine_and_session(db_url: str | None = None) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    url = db_url or settings.DATABASE_URL
    # For SQLite, check same thread disable
    connect_args = {}
    if "sqlite" in url:
        connect_args["check_same_thread"] = False

    engine = create_async_engine(
        url,
        echo=False,
        connect_args=connect_args,
        future=True,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return engine, session_factory


engine, async_session_factory = create_engine_and_session()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db(target_engine: AsyncEngine | None = None) -> None:
    eng = target_engine or engine
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema initialized successfully.")


async def close_db(target_engine: AsyncEngine | None = None) -> None:
    eng = target_engine or engine
    await eng.dispose()
    logger.info("Database connection closed.")

