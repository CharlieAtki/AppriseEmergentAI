from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.intelligence.registry import ModelRegistry


async def sync_models(session: AsyncSession, registry: ModelRegistry) -> None:
    entries = registry.available_models()
    current_ids = [e.model_id for e in entries]

    for entry in entries:
        await session.execute(
            text("""
                INSERT INTO models (id, model_id, vendor, display_name, is_active, created_at, updated_at)
                VALUES (gen_random_uuid(), :model_id, :vendor, :display_name, true, now(), now())
                ON CONFLICT (model_id)
                DO UPDATE SET is_active = true, updated_at = now(),
                              display_name = EXCLUDED.display_name
            """),
            {"model_id": entry.model_id, "vendor": entry.vendor, "display_name": entry.display_name},
        )

    if current_ids:
        await session.execute(
            text("UPDATE models SET is_active = false WHERE model_id != ALL(:ids)"),
            {"ids": current_ids},
        )
    else:
        await session.execute(text("UPDATE models SET is_active = false"))

    await session.commit()
