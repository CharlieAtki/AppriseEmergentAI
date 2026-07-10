---
target: workspace/org coordination settings modals + header/sidebar
total_score: 26
p0_count: 0
p1_count: 2
timestamp: 2026-07-10T20-11-50Z
slug: c-components-workspaces-workspacesettingsmodal-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | No loading skeleton; inputs stay editable mid-submit |
| 2 | Match System / Real World | 3 | Fine for a technical-operator audience |
| 3 | User Control and Freedom | 2 | No unsaved-changes guard; OrgSettingsModal can't clear an override back to inherited |
| 4 | Consistency and Standards | 2 | Two different interaction models (checkbox-gated vs. always-editable) for the same field set across the two modals |
| 5 | Error Prevention | 3 | Good field-level validation; no confirmation before a cascading org-wide write |
| 6 | Recognition Rather Than Recall | 2 | OrgSettingsModal shows no provenance badge at all |
| 7 | Flexibility and Efficiency | 3 | Neutral |
| 8 | Aesthetic and Minimalist Design | 3 | Clean, on-token |
| 9 | Error Recovery | 2 | Field errors good; failed fetch leaves a dead dialog |
| 10 | Help and Documentation | 3 | Adequate |
| **Total** | | **26/40** | **Acceptable** |

## Anti-Patterns Verdict

LLM: clean, no slop tells. Deterministic scan: 1 finding, side-tab on AppSidebar.tsx:153, confirmed false positive (nav active-indicator, matches DESIGN.md spec). No browser evidence (no dev server this session).

## Overall Impression

Polish pass fixed everything asked (badge provenance, themed checkbox, tooltips, toast symmetry, dynamic max). Assessment A found a real pre-existing bug: OrgSettingsModal always submits explicit numeric values, never null, silently converting inherited platform defaults into permanent org overrides on every save. Verified against backend model_fields_set semantics.

## What's Working

1. Badge provenance fix confirmed real (platform/org/workspace distinct treatments)
2. Themed Radix Checkbox confirmed real
3. Single field-metadata source (coordinationConfigFields.ts) keeps both modals in sync

## Priority Issues

[P1] OrgSettingsModal silently converts inherited defaults into permanent overrides on every save — fix: mirror workspace modal's override-checkbox + Badge pattern. /impeccable harden
[P1] No loading skeleton or error state — dead dialog on fetch failure. /impeccable polish
[P2] No unsaved-changes guard, asymmetric with stakes. /impeccable harden
[P2] max_delegation_depth_clamped fetched but never surfaced. /impeccable clarify
[P3] Inputs stay editable mid-submit in WorkspaceSettingsModal.

## Persona Red Flags

Jordan: opens org settings to look, clicks Save out of habit, silently locks in a permanent override.
Sam: Radix Checkbox.Root wrapped in native <label> — non-standard ARIA association.
Riley: rapid checkbox toggle restores possibly-invalid prior value.

## Minor Observations

Badge.tsx fallback style visually identical to org tier style.
OrgSettingsModal doesn't import Badge at all.

## Questions to Consider

1. Which interaction model (checkbox-gated vs always-editable) is the intended long-term pattern?
2. Should the UI communicate the depth-ceiling vs threshold-no-ceiling asymmetry?
