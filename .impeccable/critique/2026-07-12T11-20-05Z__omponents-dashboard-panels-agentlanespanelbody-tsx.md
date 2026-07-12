---
target: Agent Lanes panel redesign + dashboard panel config consolidation
total_score: 22
p0_count: 0
p1_count: 2
timestamp: 2026-07-12T11-20-05Z
slug: omponents-dashboard-panels-agentlanespanelbody-tsx
---
Method: dual-agent (A: design review · B: detector + evidence, isolated sub-agents)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 1/4 | Loading and true-empty states are conflated — `PanelEmptyState` renders for both "query hasn't resolved yet" and "resolved, zero rows," so the panel briefly asserts "no activity" before real data arrives. |
| 2 | Match System / Real World | 3/4 | "No recent activity" copy is plain and correct for a technical-operator audience. |
| 3 | User Control and Freedom | 3/4 | Settings popover, remove, keyboard-move all present via the panel shell. |
| 4 | Consistency and Standards | 2/4 | New `Checkbox.Root` usages drop the `id`/`htmlFor` pairing `WorkspaceSettingsModal.tsx` established; `agent-lanes` and `emergence-signal` share the same icon in the panel registry. |
| 5 | Error Prevention | n/a | No destructive/input-validation surface in this component. |
| 6 | Recognition Rather Than Recall | 1/4 | Color is the *only* encoding for segment status/task — no legend, no icon, no shape — directly against PRODUCT.md's "no status signal by color alone" rule. |
| 7 | Flexibility and Efficiency | 3/4 | Agent filter, window, groupBy config match the sibling Agent Pool form. |
| 8 | Aesthetic and Minimalist Design | 3/4 | Guide-line-not-filled-track is a genuine improvement; matches "flat by default" system language. |
| 9 | Error Recovery | n/a | No error states in this component. |
| 10 | Help and Documentation | 2/4 | Only "documentation" for a segment is a native `title` tooltip — mouse-hover-only, no keyboard equivalent. |
| **Total (8 applicable)** | | **18/32** | Roughly equivalent to the "Acceptable — significant improvements needed" band. |

## Anti-Patterns Verdict

**LLM assessment**: Not AI slop. The pill-segment/guide-line treatment matches DESIGN.md's own "thin skill bar, fully rounded, on an elevated track" language for the Agent Node component — this is applying the system's existing visual grammar more faithfully, not inventing decoration. None of the explicit bans (side-stripes, gradient text, glassmorphism, hero-metric grids, tracked eyebrows) are present. The real issues are two specific written-down accessibility rules that got skipped under implementation speed, not generic template smell.

**Deterministic scan**: `detect.mjs --json` against all six changed files returned exit code 0 / `[]` — no findings. This is expected: the detector's rule set targets markup/CSS slop patterns (gradient text, hex-color sprawl, etc.), not domain-specific a11y rules like PRODUCT.md's color-alone ban, which requires reading the project's own stated principles rather than a generic pattern match. Manual grep cross-checks corroborate Assessment A's specific claims with hard evidence:
- 0 raw `<input type="checkbox">` remain in any of the three config forms — the branding fix is complete and verified.
- 0 `aria-*`, `id`, or `htmlFor` attributes exist anywhere in the three edited config-form files — confirms the `Checkbox.Root`/`<label>` pairing genuinely lacks the explicit association `WorkspaceSettingsModal.tsx` uses.
- 0 hard-coded hex/`rgb()` colors anywhere in `AgentLanesPanelBody.tsx`, `dashboardPanels.ts`, or `DashboardPanel.tsx` — the one inline `style={{ backgroundColor: segmentColor(...) }}` resolves through `var(--color-...)` token helpers, not raw values. No false positive here.
- `PANEL_BODY_REGISTRY` / `PANEL_CONFIG_FORM_REGISTRY` — 0 matches repo-wide. The old dual-registry is fully removed, not shadowed.

**Visual overlays**: Not available — no browser automation tool exposed in this session, and the dashboard route sits behind Clerk auth, so no live-server injection was attempted (correctly skipped rather than faked).

## Overall Impression

The core visual ask — replace blocky bars with a thinner, pill-segment lane matching your Figma reference — landed well, and the registry consolidation is a genuine structural improvement, not just a file shuffle. But two of PRODUCT.md's own explicit accessibility rules got skipped in the process: color-alone status encoding, and a loading/empty-state conflation that will visibly flicker "no activity" on every panel load. Both are the kind of thing that undermines the exact "operator trusts what they're seeing" premise the product is built around. Neither is hard to fix.

## What's Working

- **The guide-line-not-filled-track choice** (a hairline `bg-border` line instead of a solid `bg-elevated` background) directly answers your original "too blocky" complaint by making the segments themselves carry all the visual weight — this is the DESIGN.md "flat by default, glow/signal draws the eye" principle applied correctly.
- **`MIN_SEGMENT_WIDTH_PERCENT`** is a genuinely considered edge case — a 2-minute task inside a 24-hour window doesn't disappear into a sliver, and the comment explains why.
- **The registry consolidation** structurally prevents the exact bug class it targets: a panel type can no longer have metadata with no implementation, or an implementation nobody can add from the picker, because there's now one definition object instead of two lists to keep in sync.

## Priority Issues

**[P1] Color is the sole encoding for task/status identity — violates PRODUCT.md directly**
- **Why it matters**: PRODUCT.md states plainly: "No status or state signal conveyed by color alone — pair with icon, label, or shape (as Badge already does)." This panel's entire job is letting an operator "spot who is idle or overloaded" at a glance — exactly the task that breaks for a colorblind operator, or under the dashboard's dim ambient-glow theme where hue discrimination is already harder. There's also no legend anywhere, so even a sighted user must remember what each hue means.
- **Fix**: Add a small legend (dot + label, reusing the existing `Badge` pattern from DESIGN.md) near the panel header when `groupBy` is active, and expose segment status as real accessible text (`aria-label`) rather than only a mouse-only `title` tooltip.
- **Suggested command**: `/impeccable clarify` (or `/impeccable audit` for the broader a11y sweep)

**[P1] Loading state is indistinguishable from true-empty, causing a misleading pop-in**
- **Why it matters**: `AgentLanesPanelBody.tsx` treats "query hasn't resolved yet" and "resolved with zero rows" identically — both render `PanelEmptyState`. For a product whose stated success metric is "operator trusting a workforce that organises itself, because the dashboard makes that visible," a panel that briefly and falsely claims "no activity" every time it loads or the window changes works directly against that goal. The sibling `AgentPoolPanelBody.tsx` likely has the same latent pattern.
- **Fix**: Distinguish `executions === undefined` (loading — render a skeleton matching the pill geometry) from `executions !== undefined && executions.length === 0` (true empty).
- **Suggested command**: `/impeccable harden`

**[P2] New checkboxes lost the codebase's established `id`/`htmlFor` accessibility pairing**
- **Why it matters**: `WorkspaceSettingsModal.tsx` explicitly pairs `Checkbox.Root id={...}` with `<label htmlFor={...}>` — the correct pattern, since Radix's `Checkbox.Root` renders as `<button role="checkbox">`, not a native input, and implicit label-wrapping association for a `<button>` is inconsistently exposed across screen readers. All three newly-fixed config forms wrap the checkbox directly in a `<label>` with no explicit pairing — confirmed by grep (0 `id`/`htmlFor`/`aria-*` in all three files). This is a regression from the pattern being copied, not a new invention, so it's a quick, mechanical fix.
- **Fix**: Add `id={`<scope>-${agent.id}`}` to each `Checkbox.Root` and split into a sibling `<label htmlFor={...}>`, matching `WorkspaceSettingsModal.tsx` exactly.
- **Suggested command**: `/impeccable audit`

**[P2] Task-grouping palette overlaps the Agent Identity palette, right next to the agent's own avatar**
- **Why it matters**: `chartColors.ts`'s `CHART_CATEGORICAL_COLORS` opens with the identical brand/accent/highlight triplet `agentColour.ts` uses for agent identity. In `groupBy=task` mode, a task segment's color (hashed from `task_id`) can collide with the very color used for that row's own `AgentAvatar` (hashed from `agent.id`) — sitting inches apart. DESIGN.md is explicit that status colors must never intersect the identity trio "so agent identity is never confused with system status"; this is the same mistake in the other direction.
- **Fix**: Give task-grouping a palette that never intersects the three agent-identity CSS vars (there's already a `--chart-rose` precedent to extend from).
- **Suggested command**: `/impeccable colorize`

**[P3] "Coming soon" placeholder doesn't reuse `PanelEmptyState`, so unimplemented panels look like a different product**
- **Why it matters**: Three panel types (`live-feed`, `active-tasks`, `workspace-stats`) are now fully advertised in Add Panel with real descriptions but land on bare `{w}×{h} · Coming soon` text — no icon, no visual parity with every other "nothing here" state in the dashboard, which uses `PanelEmptyState`.
- **Fix**: Route the fallback through `PanelEmptyState` with a "Coming soon" message, or badge those types directly in the Add Panel picker so they're not indistinguishable from working panels.
- **Suggested command**: `/impeccable polish`

## Persona Red Flags

**Alex (power user, monitoring a 12-agent workspace mid-incident)**: No legend for status colors means Alex must re-derive "amber = retry, red = failed" from memory at the exact moment working memory is most taxed. The loading/empty flicker (P1 above) means every resize or window-change briefly tells Alex "nothing is happening" during a live incident — exactly when that false signal is most costly. Overlapping executions on the same agent (two tasks whose windows intersect) render as unseparated absolutely-positioned divs with no lane-splitting — Alex can miss a second concurrent task entirely.

**Sam (screen-reader/keyboard-dependent operator)**: Every segment's only information is a native `title` tooltip — not focusable, not keyboard-reachable, not exposed as accessible text. Sam gets the guide line and the "No recent activity" idle rows, but zero information about what any *active* agent actually did. The three checkbox regressions (P2) may or may not announce their label depending on screen reader/browser combination. One thing that is *not* a regression, worth naming: the settings-popover trigger correctly uses `focus-visible:opacity-100` so it's keyboard-discoverable, unlike a pure `group-hover` approach would be.

## Minor Observations

- `agent-lanes` and `emergence-signal` share the identical `IconAnalytics` icon in `dashboardPanels.ts` — pick a distinct glyph so the Add Panel list stays scannable.
- `AgentLanesConfigForm.tsx` and `AgentPoolConfigForm.tsx` have near-identical agent-multiselect blocks — a shared `<AgentMultiSelect>` component would remove the duplication and mean the checkbox a11y fix only needs to land once.
- The `title` tooltip renders a raw ISO timestamp rather than a human-formatted time, inconsistent with the rest of the dashboard's caption-tier metadata.
- Two adjacent same-status segments that touch exactly at the boundary render as one seamless pill, silently hiding that two separate tasks happened.

## Questions to Consider

- If the entire point of Agent Lanes is "spot who is idle or overloaded," was the color-only/no-legend/mouse-only-tooltip design validated against an actual incident-response workflow, or only against the static Figma frame?
- The registry consolidation comment says a panel "can't half-register" — but three registered types still have metadata and no `Body`, fully visible in Add Panel. Should the registry itself refuse to list a type without a `Body` until it's ready, rather than allowing that state silently?
- DESIGN.md flags the three-color Agent Accent Rotation as "a placeholder, not a locked system" — was reusing those same three CSS vars for task-categorical chart colors deliberate, or will it need untangling the moment per-agent unique identities land?
