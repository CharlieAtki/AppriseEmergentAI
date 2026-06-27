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
