---
name: Apprise
description: Observability and configuration dashboard for a self-organising pool of AI agents
colors:
  brand-forest-50: "oklch(96% 0.02 155)"
  brand-forest-400: "oklch(67.3% 0.072 138.5)"
  brand-forest-600: "oklch(49.1% 0.057 148.8)"
  brand-forest-800: "oklch(34.2% 0.053 166.1)"
  brand-forest-850: "oklch(33.7% 0.067 169.0)"
  brand-forest-900: "oklch(29.1% 0.035 161.4)"
  brand-purple-500: "oklch(70% 0.15 280)"
  brand-amber-500: "oklch(72% 0.18 45)"
  neutral-950: "#0a0a0f"
  neutral-900: "oklch(21% 0.016 158)"
  neutral-800: "oklch(24% 0.012 160)"
  neutral-700: "#26263a"
  neutral-200: "#c8c8d8"
  neutral-100: "#ededed"
  status-success: "oklch(68% 0.18 145)"
  status-warning: "oklch(75% 0.18 70)"
  status-error: "oklch(62% 0.22 25)"
  status-info: "oklch(68% 0.16 230)"
  bg-glow-corner: "oklch(17% 0.090 152)"
  bg-sidebar: "oklch(13% 0.055 152 / 88%)"
typography:
  display:
    fontFamily: "Space Grotesk, system-ui, sans-serif"
    fontSize: "2.25rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "normal"
  heading:
    fontFamily: "Space Grotesk, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.3
  title:
    fontFamily: "Space Grotesk, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "Manrope, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Manrope, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.08em"
  caption:
    fontFamily: "Manrope, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 400
    lineHeight: 1.4
  code:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.6
rounded:
  sm: "6px"
  md: "8px"
  lg: "12px"
  full: "9999px"
spacing:
  inline-sm: "8px"
  inline-md: "12px"
  component: "16px"
  section: "24px"
motion:
  duration-fast: "100ms"
  duration-base: "150ms"
  duration-slow: "250ms"
  ease-standard: "cubic-bezier(0.4, 0, 0.2, 1)"
  spring-panel-expand:
    type: spring
    damping: 30
    stiffness: 300
  spring-page-swipe:
    type: spring
    damping: 32
    stiffness: 340
components:
  button-primary:
    backgroundColor: "{colors.brand-forest-600}"
    textColor: "{colors.neutral-950}"
    rounded: "{rounded.md}"
    padding: "8px 16px"
    typography: "{typography.body}"
  button-primary-hover:
    backgroundColor: "{colors.brand-forest-800}"
  input:
    backgroundColor: "{colors.neutral-800}"
    textColor: "{colors.neutral-100}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
  badge:
    rounded: "{rounded.full}"
    padding: "2px 10px"
    typography: "{typography.label}"
---

# Design System: Apprise

## 1. Overview

**Creative North Star: "The Living Canopy"**

Apprise's dashboard reads as an organic surface with something growing underneath it, not a static admin console. The base is a near-black forest floor (`neutral-950`), lit from one corner by a soft green glow that never fully resolves into a shape — the same radial gradient sits behind the sidebar and the page body, tying every screen back to one ambient light source. A faint crack-pattern texture sits under the sidebar and the page at 6–9% opacity: enough to read as ground with structure to it, never enough to compete with content. Onto that surface, individual elements — agent nodes, cards, hover states — pick up a colored glow of their own when they're active or interactive, as if catching light from the same source rather than being told to look important via a drop shadow.

This system explicitly rejects the generic AI-SaaS dashboard (cream backgrounds, gradient-text hero metrics, identical stat-tile grids) and the cluttered enterprise-admin panel (chrome-heavy layouts burying the one signal that matters under a dozen low-value ones). Apprise is infrastructure for a self-organising agent workforce; the interface should feel alive and precise at once — never decorative for its own sake, but never sterile either, because the thing it's showing you (agents developing specialisation without being told to) is itself an organic, emergent process.

**Key Characteristics:**
- Dark forest-green base with a single ambient glow source, not a flat black or navy
- Flat surfaces at rest; glow (not shadow darkness) signals elevation and interactivity
- A crack-pattern ground texture underneath everything, always subtle
- Space Grotesk for anything that names or labels a section; Manrope for everything read at length; JetBrains Mono for anything code-shaped
- Motion is a signal of underlying state (skill bars filling, agent nodes entering, glow appearing on hover) — never decoration layered on top of static content

## 2. Colors

A single forest-green hue carries brand identity; purple and amber exist as a secondary/tertiary rotation, not as competing brand colors.

### Primary
- **Forest 600** (`oklch(49.1% 0.057 148.8)`): the brand color. Primary buttons, active nav state, focus rings, the default agent accent.
- **Forest 800** (`oklch(34.2% 0.053 166.1)`): hover state for anything using Forest 600.

### Secondary
- **Violet Accent** (`oklch(70% 0.15 280)`): one leg of the per-agent accent rotation (see Named Rules). Not used as a general UI accent outside that context.

### Tertiary
- **Amber Highlight** (`oklch(72% 0.18 45)`): the third leg of the per-agent accent rotation. Also available as a general "needs attention" highlight distinct from the status-warning semantic color.

### Neutral
- **Canopy Black** (`#0a0a0f`, `neutral-950`): page background base.
- **Surface** (`oklch(21% 0.016 158)`, `neutral-900`): card and panel backgrounds — lifted just enough to sit above the ambient page gradient.
- **Elevated** (`oklch(24% 0.012 160)`, `neutral-800`): nested surfaces (inputs, skill-bar tracks, popovers).
- **Hover** (`#26263a`, `neutral-700`): hover background for elevated surfaces; doubles as the default border color.
- **Text Secondary** (`#c8c8d8`, `neutral-200`): de-emphasised but still-legible text (subtitles, secondary labels).
- **Text Primary** (`#ededed`, `neutral-100`): default foreground text.

### Status
- **Success** (`oklch(68% 0.18 145)`) · **Warning** (`oklch(75% 0.18 70)`) · **Error** (`oklch(62% 0.22 25)`) · **Info** (`oklch(68% 0.16 230)`) — reserved for system state (workspace active/inactive, task outcome, form errors). Never used for the per-agent accent rotation, which stays entirely in the brand/accent/highlight trio so agent identity is never confused with system status.

### Named Rules
**The Agent Accent Rotation.** Every agent gets one of Forest 600 / Violet Accent / Amber Highlight, deterministically hashed from its ID (`lib/agentColour.ts`), applied consistently to its avatar background, hover ring, and node glow so the same agent is recognisable at a glance across the dashboard. **This is a placeholder mechanic, not a locked system** — the intent is to move toward unique, organic per-agent visual identities (in the spirit of the Apprise mark: alive, green-forward) once that work lands; the three-color rotation is what fills that role today.

**The One Light Source Rule.** Every glow in the interface — the page background gradient, the sidebar tint, card/node hover glows — reads as light from the same origin. Don't introduce a second, differently-colored glow source; extend the existing one.

## 3. Typography

**Display Font:** Space Grotesk (with system-ui, sans-serif fallback)
**Body Font:** Manrope (with system-ui, sans-serif fallback)
**Label/Mono Font:** JetBrains Mono (monospace fallback)

**Character:** Space Grotesk is geometric and slightly technical — used only where text is naming something (page titles, dialog titles, section headers). Manrope is humanist and easy at small sizes — used for everything meant to be read, not just scanned. The pairing is a contrast pair (geometric display + humanist body), not two similar sans-serifs competing for the same job.

### Hierarchy
- **Display** (600, 2.25rem/36px, line-height 1.2): reserved for the largest page-level moments; rare in a dense dashboard.
- **Heading** (600, 1.5rem/24px, line-height 1.3): section-level headers.
- **Title** (600, 1rem/16px, line-height 1.4): dialog titles, card titles, agent node names — all `h1`–`h6` elements pick up Space Grotesk automatically.
- **Body** (400, 0.875rem/14px, line-height 1.5): default reading text. Cap prose width at 65–75ch where it appears in longer form (field descriptions, empty states).
- **Label** (600, 0.75rem/12px, letter-spacing 0.08em, uppercase where used as a section eyebrow): field labels, nav section headers.
- **Caption** (400, 0.6875rem/11px): metadata, timestamps, skill-bar values — the smallest legible tier.
- **Code** (400, 0.8125rem/13px, JetBrains Mono): anything code-shaped — IDs, technical values.

### Named Rules
**The Naming Font Rule.** Space Grotesk appears only on things that name or title something (an `h1`–`h6`, a Dialog.Title, a card heading). Everything else — body copy, labels, buttons, form fields — stays in Manrope. Don't reach for Space Grotesk to add emphasis; use weight instead.

## 4. Elevation

Apprise is flat by default and uses colored glow, not shadow darkness, to signal elevation and interactivity — consistent with the One Light Source Rule in Colors. A card at rest has a 1px border and a plain surface background; nothing about it says "raised." On hover or focus, a card or agent node picks up a 1px ring in its accent color plus a soft, accent-tinted glow radiating from the same corner the page's ambient light comes from. Dialogs are the one place a true shadow appears (`shadow-xl`), because they sit in an explicit overlay layer above the rest of the interface, not because they're "elevated" within the flow.

### Shadow Vocabulary
- **Hover glow** (`box-shadow: 0 0 0 1px var(--color-brand), 0 8px 24px oklch(from var(--glow-shadow) l c h / 0.4)`): the default interactive-surface treatment — workspace cards, agent nodes. Substitutes the agent's own accent color for `--color-brand` when the surface represents a specific agent.
- **Dialog shadow** (`shadow-xl`, Tailwind default): the only conventional drop shadow in the system, reserved for the overlay layer.

### Named Rules
**The Glow-Not-Shadow Rule.** Depth is never communicated by making a shadow darker or a surface lighter. It's communicated by a colored glow appearing where there wasn't one — the visual vocabulary of something lighting up, not something lifting off the page.

## 5. Motion

Motion is a signal of underlying state — skill bars filling, agent nodes entering, a panel's own data arriving — never decoration layered on top of static content. Two curves cover every case in the system; nothing else should be introduced without a reason tied to a specific state change.

### Duration + Easing (`--duration-*`, `--ease-standard`)

Plain CSS transitions on hover/focus states — button backgrounds, icon reveals, border color shifts — use one of three durations (`fast` 100ms, `base` 150ms, `slow` 250ms) with `ease-standard` (`cubic-bezier(0.4, 0, 0.2, 1)`). This is also the curve behind `cardEntrance` (`frontend/src/lib/motion.ts`), the staggered fade-and-rise-in used when a group of cards mounts together (dashboard panels, workspace list).

### Springs (`panelExpandSpring`, `pageSwipeSpring`)

Interactions that track a physical gesture or a shared-element layout change use a spring instead of a fixed duration, so the motion responds naturally to interruption:

- **`panelExpandSpring`** (damping 30, stiffness 300) — every `layoutId` shared-element expand/collapse (Agent Pool sparkline↔chart, Live Task Feed row↔detail).
- **`pageSwipeSpring`** (damping 32, stiffness 340) — the dashboard's page-swipe transition, slightly snappier since it's settling a drag gesture rather than a layout change.

Both live as named exports in `frontend/src/lib/motion.ts` — never hand-copy `{ damping, stiffness }` inline.

### Reduced Motion

Every framer-motion element checks `useReducedMotion()` and collapses its transition to `{ duration: 0 }` (or skips straight to the `visible`/end state for variants). This is deliberately separate from the one global `prefers-reduced-motion` CSS media query, which only governs `react-grid-layout`'s own internal reflow transition — a library-owned animation with no framer-motion hook to attach to.

## 6. Components

### Buttons
- **Shape:** 8px radius (`rounded-md`) for primary/secondary actions; icon-only buttons in dense contexts (agent node action strip) use the same radius at smaller padding.
- **Primary:** Forest 600 background, near-black text, 8px/16px padding, Manrope body weight.
- **Hover:** background shifts to Forest 800; 150ms `ease-standard` transition.
- **Secondary / Ghost:** no background at rest; muted text; hover reveals `bg-hover` (secondary) or just a text-color shift to foreground (ghost/text-only, e.g. dialog Cancel).
- **Destructive:** ghost by default, hover reveals `bg-error/10` background with error-colored text and icon (used throughout agent action strips for deactivate/delete).

### Cards
- **Corner style:** 12px radius (`rounded-xl`) for content-bearing cards (agent nodes); 8px (`rounded-lg`) for simpler cards (workspace tiles).
- **Background:** Surface (`neutral-900`), flat.
- **Border:** 1px, `border-default` (`neutral-700`) at rest.
- **Shadow strategy:** see Elevation — hover glow only, never a resting shadow.
- **Internal padding:** 12px (agent node body) to 16px (dialog content), with an internal divider (`border-border-subtle`) separating a card's action strip from its body.

### Inputs / Fields
- **Style:** `neutral-800` background, `border-default` 1px border, 8px radius.
- **Focus:** border shifts to Forest 600 plus a 1px Forest 600 focus ring — no glow on focus, glow is reserved for hover/active surfaces, not form focus states.
- **Placeholder:** muted text color, same contrast rules as body text (≥4.5:1).

### Badges / Status Pills
- **Style:** fully rounded (`rounded-full`), a small leading dot (`w-1.5 h-1.5 rounded-full bg-current`) plus label text — status is never color-alone, per the Accessibility principle in PRODUCT.md.
- **Color:** tinted background at 10% opacity of the status/source color, full-opacity text and dot in that color (`bg-success/10 text-success`, etc.).

### Navigation (Sidebar)
- **Style:** active item gets a 2px left border in Forest 600 plus a 10%-opacity Forest 600 background wash; inactive items are muted text with no background; disabled items show a "Coming soon" tooltip rather than being hidden.
- **Typography:** body-size labels, Manrope, medium weight when active.
- **Texture:** the sidebar itself carries the crack-pattern texture at 9% opacity (slightly higher than the page's 6%, since the sidebar's darker semi-transparent green needs more texture to read).

### Agent Node (signature component)
The agent node is the dashboard's most distinctive component: a 256px-wide card on the ReactFlow canvas showing an agent's avatar, status badge, top skill bars (animated fill on mount), influence score, and an action strip. Its accent color comes from the Agent Accent Rotation (Colors §Named Rules) and drives the hover-ring color, the avatar background tint, and the entrance-pulse ring for active agents — making each agent visually distinct without any manual styling per agent. Skill bars are thin (4px), fully rounded, animate their width in on mount with a spring-eased fill in the agent's accent color over an `elevated`-colored track.

## 6. Do's and Don'ts

### Do:
- **Do** use a colored glow (accent-tinted `box-shadow`) to signal hover/interactive state on cards and nodes, sourced from the same ambient light direction as the page background.
- **Do** keep Space Grotesk scoped to things that name or title something; everything else is Manrope.
- **Do** pair every status/state signal with a non-color cue (a leading dot plus label text, an icon) — never color alone.
- **Do** let the per-agent accent color (brand / accent / highlight rotation) carry through avatar, ring, and glow consistently for a given agent, so it reads as identity, not decoration.
- **Do** keep surfaces flat at rest — border only, no shadow — reserving all "elevation" language for hover/active glow.

### Don't:
- **Don't** use cream, beige, or any warm near-white background — this system is dark-forest-green by identity, not warm-neutral-by-AI-default.
- **Don't** use gradient text or `background-clip: text` for emphasis; use weight or the brand color as a solid fill.
- **Don't** build identical stat-tile grids or a generic "hero metric" template — this is a product register, not a SaaS marketing surface.
- **Don't** add drop-shadow-based elevation to cards or panels; that vocabulary is reserved for the dialog overlay layer only.
- **Don't** introduce a second ambient glow color distinct from the existing forest-green corner glow; extend the one light source instead.
- **Don't** treat the current three-color Agent Accent Rotation as permanent — it's a placeholder for a planned unique-per-agent identity system; don't build new features that hard-depend on there being exactly three agent accent colors.
