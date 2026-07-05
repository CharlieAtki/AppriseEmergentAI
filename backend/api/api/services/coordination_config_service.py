from __future__ import annotations

from dataclasses import dataclass

from core.config import settings
from core.config.coordination import CoordinationPlatformDefaults
from core.coordination.config import ConfigSource, resolve_coordination_config
from core.models.tenant import Organisation, Workspace
from core.repositories.org_repository import OrganisationRepository
from core.repositories.workspace_repository import WorkspaceRepository


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
        org_override: dict | None,
        workspace_override: dict | None,
    ) -> CoordinationConfigData:
        """Resolve + assemble in one step — the DTO builds itself, matching the
        from_domain() convention every other service DTO in this codebase uses."""
        resolved = resolve_coordination_config(platform, org_override, workspace_override)
        org_override = org_override or {}
        workspace_override = workspace_override or {}
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
            org_max_delegation_depth_override=org_override.get("max_delegation_depth"),
            org_decompose_difficulty_threshold_override=org_override.get(
                "decompose_difficulty_threshold"
            ),
            workspace_max_delegation_depth_override=workspace_override.get("max_delegation_depth"),
            workspace_decompose_difficulty_threshold_override=workspace_override.get(
                "decompose_difficulty_threshold"
            ),
        )


def _coordination_override(config: dict | None) -> dict | None:
    return (config or {}).get("coordination")


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
    existing_config: dict | None, cmd: SetCoordinationOverrideCommand
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
            settings.coordination, _coordination_override(org.config), None
        )

    async def get_for_workspace(self, workspace: Workspace) -> CoordinationConfigData:
        org = await self._org_repo.get_by_id(workspace.organisation_id)
        org_override = _coordination_override(org.config) if org else None
        workspace_override = _coordination_override(workspace.config)
        return CoordinationConfigData.from_overrides(
            settings.coordination, org_override, workspace_override
        )

    async def set_org_override(
        self, org: Organisation, cmd: SetCoordinationOverrideCommand
    ) -> CoordinationConfigData:
        coordination = _merge_coordination_override(org.config, cmd)
        org.config = {**(org.config or {}), "coordination": coordination}
        await self._org_repo.save(org)
        return CoordinationConfigData.from_overrides(settings.coordination, coordination, None)

    async def set_workspace_override(
        self, workspace: Workspace, cmd: SetCoordinationOverrideCommand
    ) -> CoordinationConfigData:
        coordination = _merge_coordination_override(workspace.config, cmd)
        workspace.config = {**(workspace.config or {}), "coordination": coordination}
        await self._workspace_repo.save(workspace)

        org = await self._org_repo.get_by_id(workspace.organisation_id)
        org_override = _coordination_override(org.config) if org else None
        return CoordinationConfigData.from_overrides(
            settings.coordination, org_override, coordination
        )
