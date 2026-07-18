from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.config import settings
from core.config.coordination import CoordinationPlatformDefaults
from core.coordination.config import resolve_coordination_config
from core.repositories.org_repository import OrganisationRepository
from core.repositories.workspace_repository import WorkspaceRepository

if TYPE_CHECKING:
    from core.coordination.config import ConfigSource
    from core.models.tenant import Organisation, Workspace


@dataclass(frozen=True)
class SetCoordinationOverrideCommand:
    """Partial update intent — used for both org- and workspace-level overrides,
    which accept an identical shape. `<field>_set=False` means the field was
    omitted from the PATCH body and must be left untouched; `_set=True` with
    value=None means the field was explicitly cleared back to inherited."""

    max_delegation_depth: int | None
    max_delegation_depth_set: bool
    decompose_difficulty_threshold: float | None
    decompose_difficulty_threshold_set: bool


@dataclass(frozen=True)
class CoordinationOverride:
    """Validated coordination values parsed from one persisted JSONB config."""

    max_delegation_depth: int | None = None
    decompose_difficulty_threshold: float | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: object | None) -> CoordinationOverride:
        if config is None:
            return cls()
        if not isinstance(config, Mapping):
            raise ValueError("coordination config must be a mapping")
        raw_override = config.get("coordination")
        if raw_override is None:
            return cls()
        if not isinstance(raw_override, Mapping):
            raise ValueError("coordination override must be a mapping")
        depth = raw_override.get("max_delegation_depth")
        if depth is not None and (type(depth) is not int or depth <= 0):
            raise ValueError("max_delegation_depth must be a positive integer")
        threshold = raw_override.get("decompose_difficulty_threshold")
        if threshold is not None and (
            isinstance(threshold, bool) or not isinstance(threshold, int | float) or threshold < 0
        ):
            raise ValueError("decompose_difficulty_threshold must be non-negative")
        return cls(
            max_delegation_depth=depth,
            decompose_difficulty_threshold=float(threshold) if threshold is not None else None,
            extra={
                key: value
                for key, value in raw_override.items()
                if key not in {"max_delegation_depth", "decompose_difficulty_threshold"}
            },
        )

    def to_mapping(self) -> dict[str, Any]:
        override = dict(self.extra)
        if self.max_delegation_depth is not None:
            override["max_delegation_depth"] = self.max_delegation_depth
        if self.decompose_difficulty_threshold is not None:
            override["decompose_difficulty_threshold"] = self.decompose_difficulty_threshold
        return override


@dataclass(frozen=True)
class CoordinationConfigData:
    """Provenance-carrying response DTO — lets a settings UI show what's inherited
    vs. overridden, and the platform ceiling, without a second round trip."""

    effective_max_delegation_depth: int
    effective_decompose_difficulty_threshold: float
    max_delegation_depth_source: ConfigSource
    decompose_difficulty_threshold_source: ConfigSource
    max_delegation_depth_clamped: bool
    platform_max_delegation_depth_default: int
    platform_max_delegation_depth_ceiling: int
    platform_decompose_difficulty_threshold_default: float
    org_max_delegation_depth_override: int | None
    org_decompose_difficulty_threshold_override: float | None
    workspace_max_delegation_depth_override: int | None
    workspace_decompose_difficulty_threshold_override: float | None

    @classmethod
    def from_overrides(
        cls,
        platform: CoordinationPlatformDefaults,
        org_override: CoordinationOverride,
        workspace_override: CoordinationOverride,
    ) -> CoordinationConfigData:
        """Resolve + assemble in one step — the DTO builds itself, matching the
        from_domain() convention every other service DTO in this codebase uses."""
        resolved = resolve_coordination_config(
            platform, org_override.to_mapping(), workspace_override.to_mapping()
        )
        return cls(
            effective_max_delegation_depth=resolved.max_delegation_depth,
            effective_decompose_difficulty_threshold=resolved.decompose_difficulty_threshold,
            max_delegation_depth_source=resolved.max_delegation_depth_source,
            decompose_difficulty_threshold_source=resolved.decompose_difficulty_threshold_source,
            max_delegation_depth_clamped=resolved.max_delegation_depth_clamped,
            platform_max_delegation_depth_default=platform.max_delegation_depth_default,
            platform_max_delegation_depth_ceiling=platform.max_delegation_depth_ceiling,
            platform_decompose_difficulty_threshold_default=(
                platform.decompose_difficulty_threshold_default
            ),
            org_max_delegation_depth_override=org_override.max_delegation_depth,
            org_decompose_difficulty_threshold_override=org_override.decompose_difficulty_threshold,
            workspace_max_delegation_depth_override=workspace_override.max_delegation_depth,
            workspace_decompose_difficulty_threshold_override=workspace_override.decompose_difficulty_threshold,
        )


def _coordination_override(config: object | None) -> CoordinationOverride:
    return CoordinationOverride.from_config(config)


def _apply_override(
    field_set: bool, value: int | float | None, current: dict[str, int | float], key: str
) -> None:
    """Mutate `current` (a config["coordination"] dict) for one field: leave it alone
    if the field was omitted from the PATCH, remove it if explicitly cleared to None,
    otherwise set it — never touches any other key in the dict."""
    if not field_set:
        return
    if value is None:
        current.pop(key, None)
    else:
        current[key] = value


def _merge_coordination_override(
    existing_config: Mapping[str, Any] | None, cmd: SetCoordinationOverrideCommand
) -> dict[str, int | float]:
    """Pure read-modify-write over just the "coordination" sub-key of a config
    dict — never touches any other key. Shared by both set_org_override() and
    set_workspace_override() since the merge logic is identical for both tiers.

    Drops any stray null values found in the existing stored dict (self-healing,
    in case they ever got in some other way) — this service never writes one
    itself (see _apply_override, which pops the key on explicit clear instead)."""
    coordination = {
        k: v for k, v in (_coordination_override(existing_config) or {}).items() if v is not None
    }
    _apply_override(
        cmd.max_delegation_depth_set, cmd.max_delegation_depth, coordination, "max_delegation_depth"
    )
    _apply_override(
        cmd.decompose_difficulty_threshold_set,
        cmd.decompose_difficulty_threshold,
        coordination,
        "decompose_difficulty_threshold",
    )
    return coordination


def _serialize_coordination_config(
    config: object | None, override: CoordinationOverride
) -> dict[str, Any]:
    if config is None:
        config = {}
    if not isinstance(config, Mapping):
        raise ValueError("coordination config must be a mapping")
    return {**config, "coordination": override.to_mapping()}


def _merge_parsed_coordination_override(
    existing_override: CoordinationOverride, cmd: SetCoordinationOverrideCommand
) -> CoordinationOverride:
    return CoordinationOverride(
        max_delegation_depth=(
            cmd.max_delegation_depth
            if cmd.max_delegation_depth_set
            else existing_override.max_delegation_depth
        ),
        decompose_difficulty_threshold=(
            cmd.decompose_difficulty_threshold
            if cmd.decompose_difficulty_threshold_set
            else existing_override.decompose_difficulty_threshold
        ),
        extra=existing_override.extra,
    )


class CoordinationConfigService:
    """Resolves and writes ContractNet coordination guards (depth, difficulty
    threshold) across the platform/org/workspace tiers. One service for both
    tiers — they share identical shape (same fields, same clamp, same
    read-modify-write pattern); splitting by tier would only duplicate that.

    Never commits, never raises HTTPException, never imports api/schemas/.
    All merge/clamp logic is delegated to resolve_coordination_config() (via
    CoordinationConfigData.from_overrides()) so there is exactly one place the
    ceiling rule lives.
    """

    def __init__(
        self, org_repo: OrganisationRepository, workspace_repo: WorkspaceRepository
    ) -> None:
        self._org_repo = org_repo
        self._workspace_repo = workspace_repo

    async def get_for_org(self, org: Organisation) -> CoordinationConfigData:
        return CoordinationConfigData.from_overrides(
            settings.coordination, _coordination_override(org.config), CoordinationOverride()
        )

    async def get_for_workspace(self, workspace: Workspace) -> CoordinationConfigData:
        org = await self._org_repo.get_by_id(workspace.organisation_id)
        org_override = _coordination_override(org.config) if org else CoordinationOverride()
        workspace_override = _coordination_override(workspace.config)
        return CoordinationConfigData.from_overrides(
            settings.coordination, org_override, workspace_override
        )

    async def set_org_override(
        self, org: Organisation, cmd: SetCoordinationOverrideCommand
    ) -> CoordinationConfigData:
        # Re-fetch under a row lock instead of trusting `org.config` as loaded by
        # require_organisation() earlier in the request — otherwise a concurrent
        # write to an unrelated config key between that load and this save would
        # be silently clobbered by this read-modify-write. See
        # AgentRepository.get_for_update for the same pattern applied to agent.skills.
        locked_org = await self._org_repo.get_for_update(org.id)
        assert locked_org is not None  # org already loaded earlier in this request
        existing_override = _coordination_override(locked_org.config)
        coordination = _merge_parsed_coordination_override(existing_override, cmd)
        locked_org.config = _serialize_coordination_config(locked_org.config, coordination)
        await self._org_repo.save(locked_org)
        return CoordinationConfigData.from_overrides(
            settings.coordination, coordination, CoordinationOverride()
        )

    async def set_workspace_override(
        self, workspace: Workspace, cmd: SetCoordinationOverrideCommand
    ) -> CoordinationConfigData:
        # See set_org_override for why this re-fetches under a row lock rather
        # than mutating the `workspace.config` loaded earlier in the request.
        locked_ws = await self._workspace_repo.get_for_update(workspace.id)
        assert locked_ws is not None  # workspace already loaded earlier in this request
        existing_override = _coordination_override(locked_ws.config)
        coordination = _merge_parsed_coordination_override(existing_override, cmd)
        locked_ws.config = _serialize_coordination_config(locked_ws.config, coordination)
        await self._workspace_repo.save(locked_ws)

        org = await self._org_repo.get_by_id(locked_ws.organisation_id)
        org_override = _coordination_override(org.config) if org else CoordinationOverride()
        return CoordinationConfigData.from_overrides(
            settings.coordination, org_override, coordination
        )
