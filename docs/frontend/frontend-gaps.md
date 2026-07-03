# Frontend — Known Gaps

## WebSocket stream endpoint missing

The `useWorkspaceStream` hook connects to `ws://.../workspaces/{id}/stream` but the backend has no corresponding route. The `GET /workspaces/{workspace_id}/stream` WebSocket endpoint does not exist in `api/routers/workspaces.py`.

The backend already publishes the right events internally via `TaskStreamLogger` and `RedisBus` — the missing piece is a WebSocket bridge that subscribes to the Redis Stream for the workspace and forwards events to connected browser clients.

**When this is built**, the event payload shapes on the backend must be kept manually in sync with the Zod schemas in `src/hooks/useWorkspaceStream.ts`. Orval does not cover the WebSocket protocol, so there is no code generation for this contract. The backend event schema is the source of truth; the Zod union is a mirror of it.

Event types the hook already handles:

| Event type | Zod schema defined | Backend publishes |
|---|---|---|
| `task.completed` | Yes | Yes (via `TaskStreamLogger`) |
| `task.executing` | Yes | Needs verification |
| `agent.skill_updated` | Yes | Needs verification |
| `emergence.detected` | Yes | Needs verification |

---

## Agent canvas — deferred items

### Personality is a system field — never expose in UI

`Agent.personality: dict[str, float]` is a ContractNet jitter mechanism. Each key is a
domain tag (e.g. `"research"`, `"coding"`), each value a weighting float. The jitter
prevents all agents bidding identically on every task. It is set and updated by the system;
it must never appear in the spawn dialog, the agent detail panel, or any other UI surface.

### Agent detail panel

Clicking a node should slide open a right-side panel showing agent skills, influence
history, and task execution history. Deferred to Phase 2. The `AgentNode` component
marks the `onClick` handler with a `TODO` comment.

### Edge connections (agent handoff topology)

Agent-to-agent handoff edges are deferred. ReactFlow `Handle` components (source +
target on all four sides of each node) must be added in the same commit that introduces
edge data — not before — to avoid dangling UI affordances.

### Node position persistence

Layout is currently computed (radial, sorted by `created_at`). Positions reset on page
refresh and shift when new agents are added. Durable persistence requires a backend change
(a `canvas_position` field on the agent or a separate canvas model). The connection-driven
layout (dagre / ELK) introduced with edge topology will replace the radial function.

### Signal count

`AgentResponse` does not include a signal count. Deferred until the backend exposes it
via the WebSocket stream endpoint (which is itself a gap — see above).
