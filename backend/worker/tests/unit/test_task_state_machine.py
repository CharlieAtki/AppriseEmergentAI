"""Tests for TaskStateMachine — legal/illegal transitions and is_terminal.

This is the highest-leverage guard in the system. A task that escapes the
state machine into an illegal status silently corrupts execution history.
Every transition pair is parameterised so coverage doesn't require thought.
"""

from __future__ import annotations

import pytest
from core.coordination.task_state import InvalidTaskTransition, TaskStateMachine


class _SimpleTask:
    """Minimal object satisfying the task.id / task.status contract."""

    def __init__(self, status: str) -> None:
        self.id = "task-test"
        self.status = status


# ── Legal transitions ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        ("pending", "enriching"),
        ("enriching", "open"),
        ("open", "reserved"),
        ("open", "expired"),
        ("reserved", "executing"),
        ("reserved", "open"),
        ("executing", "completed"),
        ("executing", "failed"),
        ("executing", "expired"),
        ("executing", "open"),
    ],
)
def test_legal_transition_succeeds(from_status, to_status):
    task = _SimpleTask(from_status)
    TaskStateMachine.transition(task, to_status)
    assert task.status == to_status


def test_transition_mutates_status_in_place():
    """transition() must write task.status directly — no return value matters."""
    task = _SimpleTask("open")
    TaskStateMachine.transition(task, "reserved")
    assert task.status == "reserved"


# ── Illegal transitions ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        ("pending", "executing"),
        ("pending", "completed"),
        ("enriching", "executing"),
        ("open", "completed"),
        ("open", "failed"),
        ("completed", "open"),
        ("completed", "executing"),
        ("failed", "executing"),
        ("failed", "open"),
        ("expired", "reserved"),
        ("expired", "open"),
        ("executing", "pending"),
    ],
)
def test_illegal_transition_raises(from_status, to_status):
    task = _SimpleTask(from_status)
    with pytest.raises(InvalidTaskTransition):
        TaskStateMachine.transition(task, to_status)


def test_illegal_transition_does_not_mutate_status():
    """Status must be unchanged when an illegal transition is attempted."""
    task = _SimpleTask("completed")
    with pytest.raises(InvalidTaskTransition):
        TaskStateMachine.transition(task, "open")
    assert task.status == "completed"


# ── is_terminal ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["completed", "failed", "expired"])
def test_is_terminal_true_for_terminal_statuses(status):
    assert TaskStateMachine.is_terminal(status) is True


@pytest.mark.parametrize("status", ["pending", "enriching", "open", "reserved", "executing"])
def test_is_terminal_false_for_non_terminal_statuses(status):
    assert TaskStateMachine.is_terminal(status) is False


def test_is_terminal_unknown_status_treated_as_terminal():
    """An unknown status has no TRANSITIONS entry — is_terminal returns True.

    This is intentional: unknown states must not be allowed to act as if
    they have legal next steps; treating them as terminal is the safe default.
    """
    assert TaskStateMachine.is_terminal("bogus_status") is True
