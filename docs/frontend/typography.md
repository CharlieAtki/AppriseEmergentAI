# Apprise Frontend — Typography Reference

## Architecture

The type system is defined in three tiers in `src/app/globals.css`:

| Tier | What it holds | Who references it |
| ---- | ------------- | ----------------- |
| **1b** — Primitive sizes | Raw `rem` values (`--size-display`, `--size-body`, …) | Tier 3 only |
| **2** — Semantic tokens | Named step variables (not type-related — size values come from Tier 1b directly) | Tier 3 only |
| **3** — Tailwind theme | `@theme inline` maps primitive sizes → Tailwind utilities | Components |

Components reference **only** Tier 3 utilities (`text-display`, `text-body`, etc.). Raw Tailwind size utilities (`text-xs`, `text-sm`, `text-base`) are banned in new code.

---

## The scale

| Tailwind utility | Size | Line height | When to use |
| ---------------- | ---- | ----------- | ----------- |
| `text-display` | 36px | 1.2 | Page-level hero headings. Not yet in use (Phase 2+). |
| `text-heading` | 24px | 1.3 | Section headings within a page. Not yet in use (Phase 2+). |
| `text-title` | 16px | 1.4 | Dialog titles, page section names (`<h1>` in headers). |
| `text-body` | 14px | 1.5 | Body copy, inputs, button text, nav items, descriptions. |
| `text-label` | 12px | 1.4 | Form labels, badge text, interactive button labels, collapsible section headings. |
| `text-caption` | 11px | 1.4 | Metadata values, validation messages, status indicators, timestamps, breadcrumbs, tooltip text. |
| `text-code` | 13px | 1.6 | Monospace IDs, webhook URLs, any code/identifier string. Always paired with `font-mono`. |

---

## Font pairing

Three fonts are loaded via `next/font/google` in `src/app/layout.tsx` and injected as CSS variables on `<html>`:

| Font | CSS variable | Tailwind token | Role |
| ---- | ------------ | -------------- | ---- |
| Space Grotesk | `--font-space-grotesk` | `--font-display` | Headings — geometric personality |
| Manrope | `--font-manrope` | `--font-sans` | All UI text — clean, neutral |
| JetBrains Mono | `--font-jetbrains` | `--font-mono` | Code, IDs, agent logs |

**Space Grotesk** is applied automatically to `h1–h6` via a CSS rule in `globals.css` — no per-component `font-display` class is needed for semantic heading elements. For non-heading elements that should read as display text, add `font-display` explicitly.

```tsx
// UI text — Manrope (default via font-sans / body)
<p className="text-body">Body text</p>

// Heading — Space Grotesk (automatic on h1/h2/h3, explicit otherwise)
<h1 className="text-title font-bold text-foreground">Overview</h1>

// Code / IDs — JetBrains Mono
<span className="text-code font-mono">workspace-uuid-here</span>
```

---

## Weight conventions

The weight scale creates a restrained hierarchy — avoid adding bold where it isn't listed.

| Context | Weight | Class |
| ------- | ------ | ----- |
| Page-level `<h1>` (WorkspaceHeader, route titles) | 700 | `font-bold` |
| Dialog titles, card headings (`text-title`) | 600 | `font-semibold` |
| `text-display`, `text-heading` | 600 | `font-semibold` |
| Navigation active item | 500 | `font-medium` |
| `text-body` in buttons | 500 | `font-medium` |
| Form labels (`text-label`) | 500 | `font-medium` |
| Section headings (`text-label uppercase`) | 600 | `font-semibold` |
| `text-body` in descriptions/copy | 400 | (no class — default) |
| `text-caption` | 400 | (no class — default) |
| `text-code` | 400 | (default — JetBrains Mono has its own weight rendering) |

---

## Tracking conventions

| Context | Class | Value |
| ------- | ----- | ----- |
| Uppercase section labels (`WORKSPACES`, `Workspace`, panel titles) | `tracking-architectural` | 0.08em |
| All other text | (default Tailwind tracking) | — |

`--tracking-architectural` is defined in `@theme inline` in `globals.css`. Do not use `tracking-wide` for uppercase labels — it is too tight (0.025em) and loses the architectural feel.

---

## Tabular numbers

For any numeric metric display (agent counts, token counts, latency figures), add `tabular-nums` to prevent layout shift as values update:

```tsx
<span className="text-body tabular-nums text-foreground">1,024</span>
```

This is a built-in Tailwind utility (`font-variant-numeric: tabular-nums`) — no custom token needed.

---

## Common patterns

### Page section heading (h1)

```tsx
<h1 className="text-title font-bold leading-tight text-foreground">{section}</h1>
```

### Dialog title + description

```tsx
<Dialog.Title className="text-title font-semibold text-foreground">
  New workspace
</Dialog.Title>
<Dialog.Description className="mt-1 text-body text-muted">
  Give your workspace a name to get started.
</Dialog.Description>
```

### Form field

```tsx
<Form.Label className="text-label font-medium text-secondary">Name</Form.Label>
<input className="text-body text-foreground …" />
<Form.Message className="text-caption text-error">Name is required.</Form.Message>
```

### Uppercase section label in sidebar or panel

```tsx
<p className="text-label font-semibold uppercase tracking-architectural text-muted">Workspace</p>
```

### Metadata list (popover / detail panel)

```tsx
<dt className="text-caption text-muted">Created</dt>
<dd className="text-caption text-secondary">{date}</dd>

<dt className="text-caption text-muted">ID</dt>
<dd className="font-mono text-code text-secondary">{id}</dd>
```

### Badge

```tsx
<span className="text-label font-medium …">Active</span>
```

### Numeric metric

```tsx
<span className="text-body tabular-nums text-foreground">1,024</span>
```

---

## What NOT to do

```tsx
// Wrong — raw Tailwind size utility
<p className="text-sm text-muted">…</p>

// Wrong — raw size on a form label
<label className="text-xs font-medium">Name</label>

// Wrong — tracking-wide on an uppercase label (too tight)
<p className="text-label uppercase tracking-wide text-muted">Workspace</p>

// Correct
<p className="text-body text-muted">…</p>
<label className="text-label font-medium">Name</label>
<p className="text-label font-semibold uppercase tracking-architectural text-muted">Workspace</p>
```

The distinction between `text-label` (12px) and `text-caption` (11px) is intentional — 1px matters at small sizes. Use `text-label` for things the user acts on or reads as a label. Use `text-caption` for supporting metadata the user reads but doesn't interact with.

---

## Adding a new step

1. Add the raw size to **Tier 1b** in `globals.css`: `--size-<name>: <value>rem;`
2. Map it in the **Tier 3** `@theme inline` block: `--text-<name>: var(--size-<name>);` plus a `--text-<name>--line-height` entry.
3. Document it in this file.

Do not skip Tier 1b — raw values belong there, not inside `@theme inline`.
