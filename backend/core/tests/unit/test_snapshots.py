"""Tests for Snapshot.from_domain's field-matching engine.

TaskSnapshot and AgentSnapshot never exercise the nested-Snapshot or
tuple-of-Snapshot branches of the base from_domain() (TaskSnapshot overrides
it entirely; AgentSnapshot has only scalar fields). These tests define local
synthetic Snapshot subclasses to drive every branch directly: scalar copy,
nested Snapshot, nullable nested Snapshot, tuple[Snapshot, ...], plain
tuple[T, ...], and the fixed-length tuple boundary case that intentionally
does NOT get element-wise snapshotting.
"""

from __future__ import annotations

import dataclasses
import types
import uuid

import pytest
from core.eventing.bus.common import Snapshot

# ── Local fixture Snapshot classes ─────────────────────────────────────────────


@dataclasses.dataclass(frozen=True, kw_only=True)
class _LeafSnapshot(Snapshot):
    id: uuid.UUID
    name: str


@dataclasses.dataclass(frozen=True, kw_only=True)
class _NestedSnapshot(Snapshot):
    id: uuid.UUID
    leaf: _LeafSnapshot


@dataclasses.dataclass(frozen=True, kw_only=True)
class _NullableNestedSnapshot(Snapshot):
    id: uuid.UUID
    leaf: _LeafSnapshot | None


@dataclasses.dataclass(frozen=True, kw_only=True)
class _TupleOfSnapshotsSnapshot(Snapshot):
    id: uuid.UUID
    leaves: tuple[_LeafSnapshot, ...]


@dataclasses.dataclass(frozen=True, kw_only=True)
class _PlainTupleSnapshot(Snapshot):
    id: uuid.UUID
    tags: tuple[str, ...]


@dataclasses.dataclass(frozen=True, kw_only=True)
class _FixedLengthTupleSnapshot(Snapshot):
    id: uuid.UUID
    pair: tuple[_LeafSnapshot, _LeafSnapshot]


def _leaf_domain(**overrides) -> types.SimpleNamespace:
    defaults = dict(id=uuid.uuid4(), name="leaf")
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


# ── Scalar fields ───────────────────────────────────────────────────────────────


def test_scalar_fields_are_copied_directly():
    domain = _leaf_domain(id=uuid.uuid4(), name="alice")
    snap = _LeafSnapshot.from_domain(domain)
    assert snap.id == domain.id
    assert snap.name == "alice"


# ── Nested Snapshot ──────────────────────────────────────────────────────────────


def test_nested_snapshot_field_recurses_via_from_domain():
    leaf = _leaf_domain(name="child")
    domain = types.SimpleNamespace(id=uuid.uuid4(), leaf=leaf)

    snap = _NestedSnapshot.from_domain(domain)

    assert isinstance(snap.leaf, _LeafSnapshot)
    assert snap.leaf.name == "child"
    assert snap.leaf.id == leaf.id


def test_nullable_nested_snapshot_present_value_is_snapshotted():
    leaf = _leaf_domain(name="present")
    domain = types.SimpleNamespace(id=uuid.uuid4(), leaf=leaf)

    snap = _NullableNestedSnapshot.from_domain(domain)

    assert isinstance(snap.leaf, _LeafSnapshot)
    assert snap.leaf.name == "present"


def test_nullable_nested_snapshot_none_value_stays_none():
    domain = types.SimpleNamespace(id=uuid.uuid4(), leaf=None)

    snap = _NullableNestedSnapshot.from_domain(domain)

    assert snap.leaf is None


def test_non_nullable_nested_snapshot_none_value_raises():
    """A field typed as a bare Snapshot subclass (no `| None`) does not get the
    None short-circuit — from_domain(None) is attempted and fails on the first
    getattr. This documents current behaviour: the hint must be Optional for a
    None domain value to be handled gracefully."""
    domain = types.SimpleNamespace(id=uuid.uuid4(), leaf=None)

    with pytest.raises(AttributeError):
        _NestedSnapshot.from_domain(domain)


# ── tuple[Snapshot, ...] ──────────────────────────────────────────────────────


def test_tuple_of_snapshots_converts_every_element():
    leaves = [_leaf_domain(name="a"), _leaf_domain(name="b")]
    domain = types.SimpleNamespace(id=uuid.uuid4(), leaves=leaves)

    snap = _TupleOfSnapshotsSnapshot.from_domain(domain)

    assert isinstance(snap.leaves, tuple)
    assert all(isinstance(leaf, _LeafSnapshot) for leaf in snap.leaves)
    assert [leaf.name for leaf in snap.leaves] == ["a", "b"]


def test_tuple_of_snapshots_accepts_any_iterable_not_just_a_tuple():
    """The domain object may hand back a list (e.g. an ORM relationship) —
    from_domain must materialise it as a tuple regardless of input container type."""
    leaves = (leaf for leaf in [_leaf_domain(name="gen")])  # generator, not list/tuple
    domain = types.SimpleNamespace(id=uuid.uuid4(), leaves=leaves)

    snap = _TupleOfSnapshotsSnapshot.from_domain(domain)

    assert snap.leaves[0].name == "gen"


def test_tuple_of_snapshots_empty_collection():
    domain = types.SimpleNamespace(id=uuid.uuid4(), leaves=[])
    snap = _TupleOfSnapshotsSnapshot.from_domain(domain)
    assert snap.leaves == ()


# ── plain tuple[T, ...] ─────────────────────────────────────────────────────────


def test_plain_tuple_field_materialises_from_a_list():
    domain = types.SimpleNamespace(id=uuid.uuid4(), tags=["a", "b", "c"])
    snap = _PlainTupleSnapshot.from_domain(domain)
    assert snap.tags == ("a", "b", "c")


def test_plain_tuple_field_from_an_already_tuple_value():
    domain = types.SimpleNamespace(id=uuid.uuid4(), tags=("x", "y"))
    snap = _PlainTupleSnapshot.from_domain(domain)
    assert snap.tags == ("x", "y")


# ── Boundary case: fixed-length tuple is NOT element-wise snapshotted ───────────


def test_fixed_length_tuple_of_snapshots_is_not_snapshotted_element_wise():
    """tuple[Snapshot, Snapshot] (no `...`) does not match the tuple[T, ...]
    unwrap — it falls through to the plain-tuple branch, so elements are copied
    as-is (still raw domain objects), NOT converted to _LeafSnapshot. This is a
    real boundary in _unwrap_tuple_snapshot_type worth locking in explicitly:
    only the `tuple[T, ...]` shape gets element-wise from_domain()."""
    leaf1, leaf2 = _leaf_domain(name="one"), _leaf_domain(name="two")
    domain = types.SimpleNamespace(id=uuid.uuid4(), pair=(leaf1, leaf2))

    snap = _FixedLengthTupleSnapshot.from_domain(domain)

    assert snap.pair == (leaf1, leaf2)
    assert not isinstance(snap.pair[0], _LeafSnapshot)


# ── Inheritance chain ────────────────────────────────────────────────────────────


def test_from_domain_covers_fields_from_base_and_subclass():
    """Fields declared on a Snapshot subclass-of-a-subclass must all be picked
    up — from_domain uses get_type_hints/fields(cls), which walks the MRO."""

    @dataclasses.dataclass(frozen=True, kw_only=True)
    class _ExtendedLeafSnapshot(_LeafSnapshot):
        extra: str

    domain = types.SimpleNamespace(id=uuid.uuid4(), name="base-field", extra="sub-field")
    snap = _ExtendedLeafSnapshot.from_domain(domain)

    assert snap.name == "base-field"
    assert snap.extra == "sub-field"
