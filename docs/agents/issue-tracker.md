# Issue tracker: Linear

Issues, gaps, and project context live in **Linear** (https://linear.app/apprise-labs). Linear is the single source of truth for all open work. Use the Linear MCP server (`linear-server`) for all issue operations.

## Projects

| Project | Scope |
|---------|-------|
| **Apprise Platform Core** | Worker jobs, memory tiers, event bus, audit log |
| **Apprise API** | HTTP layer — endpoints, auth, enrichment, WebSocket bridge, ingestion |
| **Apprise FE - Phase One** | Frontend dashboard, agent canvas, WebSocket UI |

## Labels

**Type:** Bug · Improvement · Feature
**Area:** Area: Worker · Area: Memory · Area: Event Bus · Area: API · Area: Auth · Area: Enrichment · Area: Ingestion · Area: Frontend

## Conventions

- **Create an issue**: use `mcp__linear-server__save_issue` with `title`, `team`, `project`, `priority`, `labels`, and a markdown `description` that includes a **What**, **Why it matters**, and **Spec / ADR** section linking to the relevant Notion page.
- **Read an issue**: use `mcp__linear-server__get_issue` with the issue identifier (e.g. `APP-6`).
- **List issues**: use `mcp__linear-server__list_issues` filtered by project or label.
- **Update an issue**: use `mcp__linear-server__save_issue` with `id` set to the issue identifier.
- **Add a comment**: use `mcp__linear-server__save_comment`.

## Priority mapping

| Linear priority | Meaning |
|-----------------|---------|
| Urgent (1) | Causes silent data loss or task failures; blocks the live dashboard |
| High (2) | Emergence cannot work correctly without this |
| Medium (3) | Customer-facing feature gap or meaningful internal debt |
| Low (4) | Deferred — revisit when phase or scale demands it |

## Notion ADR links

Every issue description should link to the relevant Notion ADR or spec page. The ADR database is at https://app.notion.com/p/31ba406c77484fd3b8736eb5cc3ccad1.

## Pull requests as a triage surface

PRs are not pulled into the triage queue. Only Linear issues go through triage.

## When a skill says "publish to the issue tracker"

Create a Linear issue via `mcp__linear-server__save_issue`.

## When a skill says "fetch the relevant ticket"

Use `mcp__linear-server__get_issue` with the APP-NNN identifier.
