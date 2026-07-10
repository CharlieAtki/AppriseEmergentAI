from __future__ import annotations

from dataclasses import dataclass

from core.config import settings
from core.config.bidding import BiddingPlatformDefaults
from core.coordination.config import ConfigSource, resolve_bidding_config
from core.models.tenant import Organisation, Workspace
from core.repositories.org_repository import OrganisationRepository
from core.repositories.workspace_repository import WorkspaceRepository


@dataclass(frozen=True)
class SetBiddingOverrideCommand:
    """Partial update intent — used for both org- and workspace-level overrides,
    which accept an identical shape. `<field>_set=False` means the field was
    omitted from the PATCH body and must be left untouched; `_set=True` with
    value=None means the field was explicitly cleared back to inherited."""

    bid_score_threshold: float | None
    bid_score_threshold_set: bool


@dataclass(frozen=True)
class BiddingConfigData:
    """Provenance-carrying response DTO — lets a settings UI show what's inherited
    vs. overridden without a second round trip."""

    effective_bid_score_threshold: float
    bid_score_threshold_source: ConfigSource
    platform_bid_score_threshold_default: float
    org_bid_score_threshold_override: float | None
    workspace_bid_score_threshold_override: float | None

    @classmethod
    def from_overrides(
        cls,
        platform: BiddingPlatformDefaults,
        org_override: dict | None,
        workspace_override: dict | None,
    ) -> BiddingConfigData:
        """Resolve + assemble in one step — the DTO builds itself, matching the
        from_domain() convention every other service DTO in this codebase uses."""
        resolved = resolve_bidding_config(platform, org_override, workspace_override)
        org_override = org_override or {}
        workspace_override = workspace_override or {}
        return cls(
            effective_bid_score_threshold=resolved.bid_score_threshold,
            bid_score_threshold_source=resolved.bid_score_threshold_source,
            platform_bid_score_threshold_default=platform.bid_score_threshold_default,
            org_bid_score_threshold_override=org_override.get("bid_score_threshold"),
            workspace_bid_score_threshold_override=workspace_override.get("bid_score_threshold"),
        )


def _bidding_override(config: dict | None) -> dict | None:
    return (config or {}).get("bidding")


def _apply_override(
    field_set: bool, value: float | None, current: dict[str, float], key: str
) -> None:
    """Mutate `current` (a config["bidding"] dict) for one field: leave it alone
    if the field was omitted from the PATCH, remove it if explicitly cleared to None,
    otherwise set it — never touches any other key in the dict."""
    if not field_set:
        return
    if value is None:
        current.pop(key, None)
    else:
        current[key] = value


def _merge_bidding_override(
    existing_config: dict | None, cmd: SetBiddingOverrideCommand
) -> dict[str, float]:
    """Pure read-modify-write over just the "bidding" sub-key of a config
    dict — never touches any other key, including a sibling "coordination" key
    on the same Organisation/Workspace.config JSONB blob.

    Drops any stray null values found in the existing stored dict (self-healing,
    in case they ever got in some other way) — this service never writes one
    itself (see _apply_override, which pops the key on explicit clear instead)."""
    bidding = {k: v for k, v in (_bidding_override(existing_config) or {}).items() if v is not None}
    _apply_override(
        cmd.bid_score_threshold_set, cmd.bid_score_threshold, bidding, "bid_score_threshold"
    )
    return bidding


class BiddingConfigService:
    """Resolves and writes ContractNet bid-scoring config across the
    platform/org/workspace tiers. Sibling to CoordinationConfigService, kept
    as a separate service (not a merged one) because bid-scoring and
    decomposition guards are distinct bounded contexts with independent write
    cadences — see Settings' own comment distinguishing them.

    Never commits, never raises HTTPException, never imports api/schemas/.
    """

    def __init__(
        self, org_repo: OrganisationRepository, workspace_repo: WorkspaceRepository
    ) -> None:
        self._org_repo = org_repo
        self._workspace_repo = workspace_repo

    async def get_for_org(self, org: Organisation) -> BiddingConfigData:
        return BiddingConfigData.from_overrides(
            settings.bidding, _bidding_override(org.config), None
        )

    async def get_for_workspace(self, workspace: Workspace) -> BiddingConfigData:
        org = await self._org_repo.get_by_id(workspace.organisation_id)
        org_override = _bidding_override(org.config) if org else None
        workspace_override = _bidding_override(workspace.config)
        return BiddingConfigData.from_overrides(settings.bidding, org_override, workspace_override)

    async def set_org_override(
        self, org: Organisation, cmd: SetBiddingOverrideCommand
    ) -> BiddingConfigData:
        bidding = _merge_bidding_override(org.config, cmd)
        org.config = {**(org.config or {}), "bidding": bidding}
        await self._org_repo.save(org)
        return BiddingConfigData.from_overrides(settings.bidding, bidding, None)

    async def set_workspace_override(
        self, workspace: Workspace, cmd: SetBiddingOverrideCommand
    ) -> BiddingConfigData:
        bidding = _merge_bidding_override(workspace.config, cmd)
        workspace.config = {**(workspace.config or {}), "bidding": bidding}
        await self._workspace_repo.save(workspace)

        org = await self._org_repo.get_by_id(workspace.organisation_id)
        org_override = _bidding_override(org.config) if org else None
        return BiddingConfigData.from_overrides(settings.bidding, org_override, bidding)
