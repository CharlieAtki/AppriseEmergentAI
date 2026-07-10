# Product

## Register

product

## Platform

web

## Users

Technical operators at customer organisations — engineering team leads, ops managers, technical founders — who deploy and run a workspace of AI agents against their organisation's stream of work. They connect tools, submit tasks, configure how the coordination system behaves, and watch how the agent pool develops specialisations over time. The job to be done on any given screen is either configuring how the workspace runs (tools, coordination limits, org/workspace defaults) or observing what the agent pool is actually doing (task flow, skill emergence, which agents are winning which work and why).

## Product Purpose

Apprise deploys a pool of AI agents against an organisation's work without pre-assigning roles. Agents bid on tasks through ContractNet coordination, execute using workspace tools, and develop specialisations that reflect what the workspace actually needs — a debugging specialist emerges from a stream of bug reports, a research generalist emerges from varied research briefs, entirely through accumulated experience rather than manual configuration. This dashboard (Phase 1, "Apprise Volume") is the observability and configuration layer on top of that system: where operators watch specialisation concentrate, trace why an agent behaved the way it did, and tune the coordination system that governs delegation and decomposition. Success is an operator trusting a workforce that organises itself, because the dashboard makes that self-organisation visible and controllable rather than opaque.

## Positioning

Apprise's agents organise themselves — this dashboard is how the people running them see it happening and trust it, rather than a config panel bolted onto infrastructure they can't observe.

## Brand Personality

Alive, organic, emergent. The interface should read as a living system organising itself, not a static admin panel that happens to list agents. Motion and visual language should be earned by what's actually happening underneath — specialisation concentrating, work routing toward capability — rather than decorative.

## Anti-references

Not a generic AI-SaaS dashboard: no cream/beige backgrounds, no gradient-text hero metrics, no identical stat-tile grids repeated for their own sake. Not a cluttered enterprise admin panel either (old-school Jira/Salesforce): no chrome-heavy layouts that bury the one number that matters under a dozen low-signal panels.

## Design Principles

- **Legibility over density.** The signal that matters — specialisation emerging, a config value drifting from its inherited default — should never be buried under chrome or competing with panels nobody needs right now.
- **Show the system organising itself.** Self-organisation is the product's core differentiator, not a background detail. Agents should read as a living pool with emerging structure, not a static resource table.
- **Trust through traceable provenance.** Every effective value (a skill score, a coordination limit) should trace to its source — which agent's experience produced it, which tier (platform/org/workspace) a config value inherited from. Operators should never have to guess why the system is behaving a certain way.
- **Restraint as identity.** The existing dark, technical, OKLCH-token visual system is the brand. Don't reach for AI-SaaS decoration (glassmorphism, gradient accents, tiny tracked eyebrows) to signal "product" — the understatement is the point.

## Accessibility & Inclusion

WCAG 2.1 AA. Respect `prefers-reduced-motion` for all emergence/live-update animation. No status or state signal conveyed by color alone — pair with icon, label, or shape (as `Badge` already does with a leading dot + text, not color fill alone).
