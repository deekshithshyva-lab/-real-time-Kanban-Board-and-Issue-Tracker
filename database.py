"""Async SQLAlchemy engine, session factory and declarative base."""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

engine = create_async_engine(
    settings.database_url, pool_size=10, max_overflow=20, pool_pre_ping=True
)
# expire_on_commit=False: attributes stay readable after commit (no implicit lazy IO in async).
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
