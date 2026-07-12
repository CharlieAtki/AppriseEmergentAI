# Frontend stack migration — handoff

Branch: `frontend/feature/APP-47/overview-dashboard-grid`. Plan file (approved, full detail): `C:\Users\juzat\.claude\plans\okay-now-focusing-mossy-meerkat.md`.

User directive: run all 6 phases autonomously, no further check-ins needed unless genuinely blocked. User has twice explicitly overridden the "keep custom X" recommendation in favor of the shadcn-native option (chart primitives, sonner toasts) — don't re-litigate those, just execute.

## Done (Phases 0–2) — typecheck-clean, radix/lucide fully removed

- **Phase 0**: `bunx shadcn@latest init -b base -t next -p nova -y` run. `components.json` created (note: its `iconLibrary: "lucide"` field is stale, should say phosphor — not yet fixed, flag in Phase 5). `globals.css` re-wired so shadcn's semantic vars (`--color-card`, `--color-primary`, `--color-chart-1..5`, `--radius-*`, sidebar vars) point at the existing OKLCH Tier-2 tokens instead of the generic greyscale shadcn tried to write. `layout.tsx` font reverted from shadcn's Geist back to Manrope/Space Grotesk/JetBrains Mono.
- **Phase 1**: Phosphor icons live via `frontend/src/lib/icons.ts` (re-exports, same `Icon*` alias names as before) + `frontend/src/lib/iconConfig.ts` (`ICON_WEIGHT = 'duotone'`, one constant, swappable). `IconContext.Provider` wired in `providers.tsx`. All lucide bypass imports fixed. `lucide-react` removed from package.json.
- **Phase 2**: All 9 Radix packages removed from package.json (`bun remove` confirmed "9 packages removed"). Dialog/AlertDialog/Checkbox/Popover/Select/Tooltip/Field(Form)/sonner(Toast) all migrated to Base UI + shadcn wrappers in `frontend/src/components/ui/`. Deduped: `ConfirmDeleteDialog.tsx` (shared by Delete{Workspace,Agent}Dialog). Toast migrated fully to sonner — `useAutoDismissToast.ts` and `stores/toast.ts` deleted; custom countdown-bar UI is gone (sonner has no equivalent), undo action still works via sonner's `action` prop. Forms use manual `submitted` boolean + derived `xMissing` flags for validation (shadcn's Field/FieldError has no Radix-Form-style validation engine).
- Verified: `bun run tsc --noEmit` clean, `bun run lint` shows only pre-existing baseline errors (confirmed via git-stash diff, not caused by this work).

**Not yet done from Phase 2**: manual browser click-through of migrated dialogs/popovers/selects/tooltips (no browser tool available this session). Flag one specific risk spot: `AgentInfoPopover.tsx` forwards a `ref` through the new `PopoverContent` wrapper for a ReactFlow capture-phase outside-click workaround — typechecks fine, but is a runtime-only concern worth a manual test first.

## In progress — Phase 3: charts → shadcn chart primitives

Just ran `bunx shadcn@latest add chart -y` → created `frontend/src/components/ui/chart.tsx` (ChartContainer/ChartTooltip/ChartTooltipContent/ChartLegend/ChartLegendContent/ChartConfig/ChartStyle) and `card.tsx`. Reviewed it: styling correctly targets `bg-background`/`text-foreground`/`border-border`/`text-muted-foreground`, which already resolve to the project's real tokens thanks to Phase 0's wiring — no re-theming needed there.

Reviewed the 3 real call sites:
- `EmergenceSignalPanelBody.tsx` — one `LineChart` with `<Tooltip content={<ChartTooltip labelFormatter=.../>} />`, single series (`gini_coefficient`, fixed color `var(--color-text-primary)`), plus `ReferenceDot` hub markers.
- `AgentPoolExpandedChart.tsx` — one `LineChart`, single series (`influence`), color from `getChartColor(agent.id)` (a **dynamic, deterministic-hash color picker**, not a fixed named series — see gotcha below), also uses `ChartTooltip`.
- `AgentPoolPanelBody.tsx` sparklines (~line 260) — bare `LineChart`+`Line`, **no tooltip at all**, no axes. Only needs `ChartContainer` wrap if anything, arguably can stay as-is or get a trivial wrap for consistency — low priority, not the focus of "the mess" the user meant.
- `AgentLanesPanelBody.tsx` — uses `ChartTooltipCard` directly (not through recharts' `content` prop) inside a Base UI `Tooltip.Content` for discrete per-segment hover, per-segment not per-chart. **This usage must survive** — don't delete `ChartTooltipCard.tsx` outright, only stop using it from the two recharts files above once shadcn's `ChartTooltipContent` replaces `ChartTooltip.tsx`.

### Key gotcha to solve before writing code (not yet resolved)

shadcn's `ChartConfig` is keyed by **fixed series/data keys** (e.g. `{ influence: { label: "Influence", color: "var(--chart-1)" } }`), styled via a generated `<style>` block that sets `--color-{key}` CSS vars scoped to the chart's `data-chart` id. But this project's actual chart coloring (`frontend/src/lib/chartColors.ts`) is **dynamic per-entity-id** — `getChartColor(agentId)` hashes an agent/task UUID into one of 5 rotating colors, because color = that agent's own identity color elsewhere in the UI (Agent Accent Rotation), not a fixed "series role" the way shadcn's chart examples assume (e.g. "revenue" is always blue). A `ChartConfig` with one static key like `influence: { color: getChartColor(agent.id) }` per-render actually works fine here (config is just a plain object, nothing stops it from being computed per-agent at render time) — this is NOT a blocker, just don't reach for the "static named `ChartConfig` object outside the component" pattern shadcn's own docs show; build the config inline/memoized per chart instance instead.

### Remaining Phase 3 work

1. In `EmergenceSignalPanelBody.tsx` and `AgentPoolExpandedChart.tsx`: replace `ResponsiveContainer` + manual `<XAxis>`/`<YAxis>`/`<Tooltip content={<ChartTooltip/>}>` boilerplate with `<ChartContainer config={...}><LineChart>...<ChartTooltip content={<ChartTooltipContent .../>} />...</LineChart></ChartContainer>`. Build one `ChartConfig` per call site (memoized, keyed by the actual dataKey used — `gini_coefficient` / `influence`), pointing `color` at the existing token/`getChartColor()` value so no new color decisions are made.
2. Delete `frontend/src/components/dashboard/panels/ChartTooltip.tsx` once both its call sites are migrated to shadcn's `ChartTooltipContent`.
3. **Keep** `ChartTooltipCard.tsx` — still used by `AgentLanesPanelBody.tsx` for discrete segment tooltips outside the recharts `content` prop pattern. Don't touch it in Phase 3.
4. Preserve `AgentPoolExpandedChart.tsx`'s `layoutId` framer-motion shared-element transition (line ~45) — must keep animating correctly from the sparkline card to the expanded chart through the `ChartContainer` wrap; this is independent of the chart-library swap and easy to accidentally break by changing the wrapping DOM structure ChartContainer introduces (`ChartContainer` renders a `div` wrapper — the `motion.div` with `layoutId` should stay the outermost element, with `ChartContainer` nested inside it, not the reverse).
5. Sparklines in `AgentPoolPanelBody.tsx`: optional, low-priority — either leave as bare recharts (no tooltip, no ChartContainer needed) or wrap for consistency; not the source of "the mess" per the original audit (that was the tooltip/boilerplate duplication in the two full-chart files, both handled by steps 1–2).
6. Verify: `bun run tsc --noEmit`, `bun run lint`, then manually confirm (browser tool needed, none available this session): Emergence Signal line + hub-marker dots render/hover correctly; Agent Pool expanded chart hover tooltip + the shared-element expand/collapse animation both still work; sparklines unaffected.

## Not started — Phase 4: config form dedup

- Extract the checkbox-list + `toggleAgent()` block duplicated in `AgentPoolConfigForm.tsx` / `AgentLanesConfigForm.tsx` into one shared `AgentMultiSelect` component, built on the Phase 2 Base UI `Checkbox` wrapper. Props: `agents`, `selectedIds`, `onToggle`.
- Extract the common `flex flex-col gap-3` labeled-section wrapper into a `ConfigSection` component (label + content), reused by all 3 config forms (`AgentPoolConfigForm`, `AgentLanesConfigForm`, `EmergenceSignalConfigForm`).
- Verify: typecheck, lint, manually reopen each panel's settings popover and confirm every field still reads/writes `panel.config` correctly (no browser tool this session — flag to user).

## Not started — Phase 5: cleanup pass

- Confirm `package.json` has zero `lucide-react` / `@radix-ui/react-*` (already true as of Phase 2, just needs final grep confirmation after Phase 3/4 touch more files).
- Fix `components.json`'s stale `iconLibrary: "lucide"` → should reflect Phosphor (cosmetic but should be a one-line fix here, not skipped).
- **Remove dead CSS** in `frontend/src/app/globals.css`: the hand-written `@keyframes dialog-overlay-in/out`, `dialog-content-in/out`, `popover-in/out` and their `[data-state="open"|"closed"]`-keyed selectors are dead code now — Base UI's generated Dialog/Popover components use boolean `data-open`/`data-closed` attributes + `tw-animate-css` utility classes instead, not these old Radix-keyed rules. Also `.animate-collapsible-down/up` keyframes (tied to the now-uninstalled Radix Collapsible, confirmed unused even before this migration) are dead. **Before deleting, grep for any remaining usage of these class names/keyframe names across `src/` to be sure nothing new started relying on them during Phase 2/3/4.**
- Full-repo `bun run tsc --noEmit` and `bun run lint`.
- Re-run `/impeccable critique` against the dashboard panels (same surfaces critiqued last session) now that the primitive layer underneath has changed, to catch regressions phase-by-phase verification didn't.
- Owed to user at this point: a consolidated list of every "no browser tool available, manually verify X" item deferred across all 5 phases (Phase 2 dialogs/popovers/selects/tooltips + the `AgentInfoPopover` ref risk; Phase 3 chart hover + expand animation; Phase 4 config form popovers) — surface this as one checklist rather than scattered mentions, since it's the single biggest "not actually done" gap in an otherwise typecheck/lint-clean migration.

## Verification commands (from `frontend/`)

```
bun run tsc --noEmit
bun run lint
bun run dev -- -p 3055   # isolated port, avoids colliding with any other running dev server on 3000
```
