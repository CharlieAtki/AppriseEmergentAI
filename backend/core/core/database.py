from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_raw_url = os.environ.get("DATABASE_URL", "postgresql://localhost/apprise")
# Ensure the asyncpg driver is used regardless of how the env var is set.
DATABASE_URL = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    session = SessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
