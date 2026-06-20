from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.observability import ProceduralKnowledgeLog


class ProceduralKnowledgeRepository:
    """Concrete ProceduralKnowledgeRepository backed by SQLAlchemy AsyncSession.

    ProceduralKnowledgeLog supports a three-phase dual-write (Postgres-first durability):
      Phase 1 — record(): insert the audit row (committed before Qdrant is touched).
      Phase 2 — Qdrant write (caller-owned, no session needed).
      Phase 3 — save(): stamp vector_store_ref after Qdrant succeeds.

    record() generates and returns the log_id so the caller can bridge Phase 1 and
    Phase 3 across separate session blocks — the ID is held as a local variable in
    the stage function. The unique partial index on execution_id is the DB backstop
    for idempotency; get_by_execution() is the application-level guard.

    Transaction contract: never calls commit(). All methods stage changes;
    the caller owns the transaction boundary via span.session().
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_execution(self, execution_id: uuid.UUID) -> ProceduralKnowledgeLog | None:
        """Idempotency check — returns existing log for this execution if present."""
        return await self._session.scalar(
            select(ProceduralKnowledgeLog).where(
                ProceduralKnowledgeLog.execution_id == execution_id
            )
        )

    async def get_by_id(self, log_id: uuid.UUID) -> ProceduralKnowledgeLog | None:
        """PK lookup — used by Phase 3 to stamp vector_store_ref after Qdrant succeeds."""
        return await self._session.get(ProceduralKnowledgeLog, log_id)

    async def record(
        self,
        workspace_id: uuid.UUID,
        agent_id: uuid.UUID,
        domain: str,
        rule_text: str,
        execution_id: uuid.UUID,
    ) -> uuid.UUID:
        """Stage Phase 1 insert. Generates and returns log_id so Phase 3 can look
        it up by PK across a different session block. Does not flush or commit."""
        log_id = uuid.uuid4()
        self._session.add(
            ProceduralKnowledgeLog(
                id=log_id,
                workspace_id=workspace_id,
                agent_id=agent_id,
                domain=domain,
                rule_text=rule_text,
                execution_id=execution_id,
            )
        )
        return log_id

    async def save(self, log: ProceduralKnowledgeLog) -> None:
        """Stage Phase 3 stamp — marks both Postgres and Qdrant writes as complete."""
        self._session.add(log)
