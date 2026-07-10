---
target: org and workspace settings
total_score: 16
p0_count: 1
p1_count: 2
timestamp: 2026-07-10T17-08-21Z
slug: nd-src-components-workspaces-workspacesettings-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 1 | `WorkspaceSettings.tsx` returns `null` while loading — blank flash, no skeleton |
| 2 | Match System / Real World | 2 | Workspace settings page has no heading — no confirmation of where you landed |
| 3 | User Control and Freedom | 1 | No Cancel/reset on the settings page; no unsaved-changes guard |
| 4 | Consistency and Standards | 1 | Org modal uses Radix `Form.*`; workspace page uses a bare `<form>` + unstyled native checkbox |
| 5 | Error Prevention | 1 | No `max` on numeric fields; empty override input submits `0` silently (`Number('')`) |
| 6 | Recognition Rather Than Recall | 2 | Source badge intent is right but broken in execution (see P0 below) |
| 7 | Flexibility and Efficiency | 2 | Adequate for current 2-field scope |
| 8 | Aesthetic and Minimalist Design | 3 | Genuinely restrained, matches DESIGN.md's flat/glow vocabulary |
| 9 | Error Recovery | 1 | Generic toast only; no distinction between network vs validation failure |
| 10 | Help and Documentation | 2 | Inline field descriptions are used well in both surfaces |
| **Total** | | **16/40** | **Poor — significant improvements needed** |

## Anti-Patterns Verdict

**LLM assessment (Assessment A):** Mostly clean — correctly reuses the `EditWorkspaceDialog` shell rather than inventing new modal vocabulary, stays within the Manrope/Space Grotesk split, no gradient text or stat-tile grids. One real tell: an unstyled native `<input type="checkbox">` in `WorkspaceSettings.tsx` sitting inside an otherwise fully-themed dark UI — reads as "finished 90%, stopped." More serious than a slop tell: the source badge (`platform`/`org`/`workspace`) silently renders identically for all three tiers because `Badge.tsx`'s `statusStyles` map only has `active`/`inactive` keys — a confident-looking but functionally broken rendering of the exact feature PRODUCT.md names as this product's differentiator.

**Deterministic scan (Assessment B):** 1 finding — `side-tab` rule on `AppSidebar.tsx:140` (`border-l-2` on an active nav item). **False positive**, confirmed by manual inspection: this is a pre-existing active-state indicator on a sidebar nav link (`rounded-r-md border-l-2 border-brand-primary bg-brand-primary/10 ...`), not a decorative card-accent stripe — the detector rule is calibrated for card side-accents, not nav active-state borders. Not part of the new settings feature and not a real issue.

**Visual overlays:** Not available — no browser automation tool exposed in this session, so no live render or overlay could be produced. All findings above are from static source review; verify visually once you can run the dev server against this in a browser.

## Overall Impression

The interaction *pattern* is right — progressive disclosure on the override checkbox is the correct design for a tiered-config UI, and the shared field schema keeps both surfaces in sync. But the feature's actual differentiator — showing *why* a value is what it is — doesn't work: the source badge renders the same color for every tier, silently. Combined with an unstyled checkbox and no loading state, this reads as functionally complete but not finished. The biggest opportunity is fixing the badge (cheap, contained) and bringing the workspace settings page up to the same form-validation standard as the org modal it's meant to mirror.

## What's Working

1. **Progressive disclosure on the override toggle** — starts read-only showing the inherited value, only unlocks editing when the user explicitly opts in. Exactly the right pattern here.
2. **Shared `coordinationConfigFields.ts` schema** driving both surfaces — prevents label/description drift between org and workspace views by construction.
3. **Dialog structure fidelity** — `OrgSettingsModal` clones the established `EditWorkspaceDialog` shell instead of inventing new modal vocabulary.

## Priority Issues

**[P0] Source badge renders identically for every provenance tier**
- **Why it matters**: PRODUCT.md names traceable provenance as the core reason this feature exists ("operators should never have to guess why the system is behaving a certain way"). `Badge.tsx`'s `statusStyles` only maps `active`/`inactive`; `platform`/`org`/`workspace` all fall through to the same blue `fallback` style. Every field's badge looks the same regardless of tier.
- **Fix**: Add `platform`/`org`/`workspace` entries to `Badge.tsx`'s `statusStyles` with genuinely distinct treatments.
- **Suggested command**: `/impeccable clarify` (or a direct fix — this is small and mechanical)

**[P1] Unstyled native checkbox breaks the dark theme**
- **Why it matters**: Every other control in this codebase is deliberately re-skinned to the forest-green system; this is the one browser-default widget left in, and it'll render as a light system checkbox against a `neutral-950` background — the "looks unfinished" tell DESIGN.md's Don'ts explicitly warn against.
- **Fix**: Themed checkbox (Radix `Checkbox` primitive, `neutral-800` bg, Forest 600 checked state, matching focus ring).
- **Suggested command**: `/impeccable polish`

**[P1] No loading state on either surface**
- **Why it matters**: `WorkspaceSettings.tsx` returns `null` while fetching (blank flash); `OrgSettingsModal` renders fields with empty values before data arrives, briefly editable before the `useEffect` sync overwrites them. Violates Visibility of System Status directly.
- **Fix**: Skeleton/spinner state for both; disable inputs until initial data resolves.
- **Suggested command**: `/impeccable polish`

**[P2] No dirty-state protection on the workspace settings page**
- **Why it matters**: Unlike the modal (bounded dismiss-or-commit), the settings page is a normal route — a user can navigate away mid-edit and silently lose work. This is an ops surface where fields are numeric thresholds someone might tune carefully.
- **Fix**: Track dirty state, show an inline "unsaved changes" indicator, add Cancel/reset.
- **Suggested command**: `/impeccable harden`

**[P2] Inconsistent, risk-inverted success feedback**
- **Why it matters**: Org settings cascade to every workspace unless overridden — the more consequential write — but the modal just closes silently on success. The narrower workspace-level save gets a toast. Feedback weight is backwards from the actual blast radius.
- **Fix**: Add a success toast to `OrgSettingsModal`'s `onSuccess`, matching `WorkspaceSettings`'s pattern.
- **Suggested command**: `/impeccable clarify`

**[P3] No client-side upper bound or inline validation on numeric fields**
- **Why it matters**: `coordinationConfigFields.ts` sets `min` but never `max`; `WorkspaceSettings.tsx` has no inline validation, so an emptied override input submits `Number('') === 0` silently — an unintended zero-depth lockout with no warning.
- **Fix**: Add `max` values to the field schema; add real-time validation feedback to `WorkspaceSettings` matching the org modal's `Form.Message` pattern.
- **Suggested command**: `/impeccable harden`

## Persona Red Flags

**Alex (Power User)**: Iterating on config values (override → tweak → revert) has no field-level saved/pending distinction — only a single page-level toast after full submit. Alex can't tell at a glance whether a reversion actually persisted without reloading mentally.

**Sam (Accessibility-Dependent)**: The gear-icon "Organisation settings" button in `AppSidebar.tsx` has an `aria-label` but isn't wrapped in the `Tooltip.Root` pattern used for every other icon-only affordance in the same file — sighted keyboard users get no visible label on focus, only screen readers get the name. Ironically, the unstyled native checkbox (P1) is the one control here that's fully keyboard/AT-accessible by default.

**Riley (Stress Tester)**: Clearing the override input to empty while checked and hitting Save sends `Number('') === 0` with zero warning — a silent unintended zero-depth lockout, bounded only by whatever the backend does with it (untested in this frontend-only review).

## Minor Observations

- `OrgSettingsModal` uses `max-w-2xl` for a 2-field form; the comparable `EditWorkspaceDialog` uses `max-w-md`. Reconcile unless the wider modal is intentional for future field growth.
- `ConfigFieldMeta.type` (`'integer' | 'float'`) is declared but never read by either consumer — dead metadata or an unfinished branch.
- `WorkspaceSettings.tsx`'s checkbox `onChange` handler (nested ternary inside an object literal inside `setState`) is dense — worth simplifying since it's the crux of the override behavior.
- The org-switcher trigger's literal `bg-white/10` (pre-existing, not part of this feature) sits directly next to the new gear button and is a visible outlier against the OKLCH-token discipline elsewhere.

## Questions to Consider

1. With no permission gating and no confirmation on save, is a silently-closing modal the right amount of ceremony for an action that can change delegation behavior across an entire org?
2. If the badge bug means every operator currently sees the same color for every tier, has this actually been looked at rendered yet? Worth an eyes-on-screen check before assuming provenance is "shipped."
3. Workspace Settings is a full page, not a dialog — why does it borrow the batch-submit-no-drafts modal interaction model instead of a page-native pattern (autosave, or a persistent unsaved-changes bar)?
