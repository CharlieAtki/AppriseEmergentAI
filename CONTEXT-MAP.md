# Context Map

## Contexts

- [Backend](./docs/backend/CONTEXT.md) — multi-tenant agent platform: workspaces, agents, tasks, coordination, observability
- [Frontend](./docs/frontend/CONTEXT.md) — live dashboard and workspace management UI

## Relationships

- **Backend → Frontend**: Backend publishes typed REST responses (OpenAPI) and dashboard-facing WebSocket events; Frontend consumes both via Orval-generated Zod schemas and a hand-maintained `WorkspaceEvent` union (WebSocket events aren't OpenAPI-covered)
