from __future__ import annotations

from fastapi import Depends, Request

from core.activity.agent_logger import AgentActivityLogger
from core.activity.base import PublishFn
from core.activity.task_logger import TaskActivityLogger
from core.bus.in_process_bus import InProcessBus


def get_bus(request: Request) -> InProcessBus:
    return request.app.state.bus  # type: ignore[no-any-return]


def get_event_publisher(bus: InProcessBus = Depends(get_bus)) -> PublishFn:
    return bus.publish


def get_task_activity_logger(
    publish: PublishFn = Depends(get_event_publisher),
) -> TaskActivityLogger:
    return TaskActivityLogger(publish)


def get_agent_activity_logger(
    publish: PublishFn = Depends(get_event_publisher),
) -> AgentActivityLogger:
    return AgentActivityLogger(publish)
