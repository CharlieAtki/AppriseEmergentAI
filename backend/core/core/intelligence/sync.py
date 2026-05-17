from __future__ import annotations

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.intelligence.registry import ModelRegistry
from core.models.intelligence import Model


async def sync_models(session: AsyncSession, registry: ModelRegistry) -> None:
    entries = registry.available_models()
    current_ids = [e.model_id for e in entries]

    for entry in entries:
        stmt = (
            pg_insert(Model)
            .values(
                model_id=entry.model_id,
                vendor=entry.vendor,
                display_name=entry.display_name,
                is_active=True,
            )
            .on_conflict_do_update(
                index_elements=["model_id"],
                set_={
                    "is_active": True,
                    "display_name": pg_insert(Model).excluded.display_name,
                    "updated_at": func.now(),
                },
            )
        )
        await session.execute(stmt)

    if current_ids:
        await session.execute(
            update(Model)
            .where(Model.model_id.not_in(current_ids))
            .values(is_active=False, updated_at=func.now())
        )
    else:
        await session.execute(
            update(Model).values(is_active=False, updated_at=func.now())
        )

    await session.commit()