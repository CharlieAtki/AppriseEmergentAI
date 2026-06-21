from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.intelligence.registry import ModelRegistry
from core.models.intelligence import Model
from core.models.tools import Tool

if TYPE_CHECKING:
    from core.agents.tooling.registry import ToolRegistry


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
        await session.execute(update(Model).values(is_active=False, updated_at=func.now()))

    await session.commit()


async def sync_tools(session: AsyncSession, registry: ToolRegistry) -> None:
    entries = registry.available_tools()
    current_keys = [(e.defn.namespace, e.defn.name) for e in entries]

    for entry in entries:
        defn = entry.defn
        stmt = (
            pg_insert(Tool)
            .values(
                namespace=defn.namespace,
                name=defn.name,
                display_name=defn.display_name,
                description=defn.description,
                category=defn.category.value,
                tool_type="platform",
                config_schema=defn.config_json_schema(),
                task_types=list(defn.task_types),
                is_active=True,
            )
            .on_conflict_do_update(
                constraint="uq_tools_namespace_name",
                set_={
                    "is_active": True,
                    "description": pg_insert(Tool).excluded.description,
                    "display_name": pg_insert(Tool).excluded.display_name,
                    "config_schema": pg_insert(Tool).excluded.config_schema,
                    "task_types": pg_insert(Tool).excluded.task_types,
                    "updated_at": func.now(),
                },
            )
        )
        await session.execute(stmt)

    if current_keys:
        await session.execute(
            update(Tool)
            .where(tuple_(Tool.namespace, Tool.name).not_in(current_keys))
            .values(is_active=False, updated_at=func.now())
        )
    else:
        await session.execute(update(Tool).values(is_active=False, updated_at=func.now()))

    await session.commit()
