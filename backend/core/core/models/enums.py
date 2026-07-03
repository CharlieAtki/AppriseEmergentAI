from __future__ import annotations

from enum import StrEnum


class AgentStatus(StrEnum):
    active = "active"
    inactive = "inactive"


class WorkspaceStatus(StrEnum):
    active = "active"
    paused = "paused"
    archived = "archived"


class TaskStatus(StrEnum):
    pending = "pending"
    enriching = "enriching"
    open = "open"
    reserved = "reserved"
    executing = "executing"
    completed = "completed"
    failed = "failed"
    expired = "expired"


class TaskPriority(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"
    critical = "critical"
