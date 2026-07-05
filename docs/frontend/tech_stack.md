# Apprise Frontend — Technical Stack Reference

## Overview

This document covers the complete frontend technical stack for the Apprise platform, the rationale behind every decision, and the key architectural patterns that tie it together. It is written for developers joining the project who are already familiar with the Apprise backend architecture — ContractNet coordination, LangGraph ReAct execution, three-tier Chroma memory, and the Redis event bus. If you have not read the Architecture Deep Dive and the Phase Roadmap documents, read those first.

The frontend serves three product phases:

- **Phase 1 — Apprise Volume**: Real-time observability dashboard for a live pool of emergent agents processing a task stream. Skill updates, emergence detection metrics, task execution state.
- **Phase 2 — Apprise Artifacts**: Tool Registry UI, artefact dependency graph viewer, fork/evaluate/merge audit trail, human-in-the-loop approval interface.
- **Phase 3 — Apprise Edge**: Fleet coordination monitoring for physical agent deployments. (Likely a much later phase)

Every tool choice in this stack accounts for all three phases. Nothing built for Phase 1 requires replacement in Phase 2 or 3 — only additions.

---

## Stack at a Glance

| Layer | Tool | Version |
|---|---|---|
| Framework | Next.js | 16 (App Router) |
| Package manager | Bun | latest |
| Language | TypeScript | 5.x strict |
| Auth | Clerk (`@clerk/nextjs`) | v7 |
| API code generation | Orval | latest |
| HTTP client | Axios | latest |
| Server state | TanStack Query | v5 |
| Client UI state | Zustand | latest |
| Runtime validation | Zod | v4 |
| Styling | Tailwind CSS | v4 |
| Headless UI primitives | Radix UI | latest (Phase 1+, install per-primitive as needed) |
| Icons | Lucide React | latest |
| Animation | Framer Motion | latest (Phase 2+, not yet installed) |
| Data visualisation | TBD | — |
| Graph / node visualisation | ReactFlow (`@xyflow/react`) | latest |
| Code editor | Monaco Editor | latest (Phase 2+, not yet installed) |
| Date utilities | date-fns | latest |

---

## Framework and Build Tooling

### Next.js 16 (App Router)

**What it is**: A React framework with file-based routing, React Server Components, and built-in support for server-side rendering and proxy (formerly middleware — renamed in v16).

**Why it was chosen**: The Apprise frontend starts as a real-time observability dashboard (Phase 1) and grows into a multi-tenant SaaS product (Phase 2) with workspace management, auth-protected routes, and a public marketing surface. A plain Vite SPA would serve Phase 1 well but would require significant rearchitecting for Phase 2's routing and auth requirements. Next.js App Router handles both without a rewrite.

The routing model is the primary justification. Workspace-scoped views map directly to nested App Router layouts:

```
app/
  layout.tsx                         # root layout — Clerk auth provider, global CSS
  page.tsx                           # workspace list (server component, SSR with prefetch)
  workspaces/
    [id]/
      layout.tsx                     # 'use client' boundary, WebSocket connection
      page.tsx                       # observability dashboard
      agents/
        [agentId]/
          page.tsx                   # agent detail
      tasks/
        page.tsx                     # task board
```

Clerk auth proxy runs at the App Router level via `src/proxy.ts`, protecting every route under `/workspaces` without boilerplate in individual page files. When Phase 2 adds a `/tools` registry route and a `/artifacts` viewer, they follow the same pattern — nested under `[id]`, inside the same client boundary.

**The client boundary strategy**: App Router pushes toward React Server Components, but the Apprise observability dashboard is almost entirely client-side — real-time data, WebSocket connections, interactive charts, agent detail panels. Rather than placing `'use client'` on every individual component, the workspace layout declares a single boundary. Every component inside `app/workspaces/[id]/` inherits the client context without its own directive.

```tsx
// app/workspaces/[id]/layout.tsx
'use client'
import { use } from 'react'
import { useWorkspaceStream } from '@/hooks/useWorkspaceStream'

export default function WorkspaceLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ id: string }>  // Next.js 16: params is a Promise in client components
}) {
  const { id } = use(params)
  useWorkspaceStream(id)  // WebSocket connection, mounted once for the entire subtree
  return <>{children}</>
}
```

`AgentGrid`, `TaskBoard`, `EmergenceChart`, and every other dashboard component sit inside this boundary. None of them need their own `'use client'` directive. The root layout and the workspace list page remain genuine server components and benefit from SSR.

**TanStack Query + SSR on the workspace list**: For the workspace list page (a server component), TanStack Query's `HydrationBoundary` pattern allows prefetching data on the server and hydrating the cache on the client. This eliminates the loading-state flash on initial navigation.

```tsx
// app/page.tsx — stays a server component
import { dehydrate, HydrationBoundary, QueryClient } from '@tanstack/react-query'

export default async function Page() {
  const queryClient = new QueryClient()
  await queryClient.prefetchQuery({
    queryKey: ['workspaces'],
    queryFn: () =>
      fetch(`${process.env.API_URL}/workspaces`).then(r => r.json()),
  })
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <WorkspaceList />
    </HydrationBoundary>
  )
}
```

This pattern applies to the workspace list only. Dashboard components inside the client boundary use TanStack Query's standard client-side hooks with no server prefetching.

---

### Bun

Used as a package manager only — not as the Next.js runtime. The Next.js server process runs on Node.js. `bun install` is significantly faster than npm or pnpm; everything else is standard.

```bash
bun install          # install dependencies
bun run dev          # next dev (runs on Node.js)
bun run build        # next build
bun run orval        # regenerate API client
bun run tsc --noEmit # type-check without emitting
```

---

### TypeScript

**Configuration**: Strict mode, no exceptions. The safety model for the Orval-generated API layer depends on TypeScript catching shape mismatches at compile time. Key settings beyond the Next.js defaults:

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true
  }
}
```

`noUncheckedIndexedAccess` is important given the volume of array indexing in chart data processing — it forces explicit bounds checking rather than allowing silent `undefined` access. No `any` without a documented reason and a `// eslint-disable` comment explaining it.

---

## API Layer

### Orval

**What it is**: A dev-only code generator that reads an OpenAPI specification and produces typed TypeScript. It produces nothing that runs at build time — the generated files are static TypeScript that the compiler processes like any other source file.

**Why it was chosen**: FastAPI automatically generates an OpenAPI 3.0 specification from Pydantic models and exposes it at `/openapi.json`. Every endpoint, request shape, and response shape is formally described there. Orval reads that specification and generates:

- Zod schemas for every named type in `src/api/generated/model/` (`.zod.ts` files). The barrel (`model/index.ts`) exports only from `.zod.ts` files — Zod schemas are the source of truth for types, not bare TypeScript interfaces.
- TanStack Query hooks for every endpoint, with a Zod schema injected as a third argument to `customInstance` on every call.
- Query key factories, invalidate helpers, `getQueryData`/`setQueryData` helpers.

The FastAPI Pydantic models are the single source of truth for the entire type system. A backend schema change propagates to the frontend at the next `bun run orval`, surfacing as TypeScript errors at the call sites where the contract broke — before it reaches a browser. If the mismatch only appears at runtime, `schema.parse(res.data)` in `customInstance` throws at the HTTP boundary.

**Named enums**: Pydantic `StrEnum` types (`AgentStatus`, `WorkspaceStatus`, `TaskStatus`, `TaskPriority`) generate named Zod enums in the barrel. Import them from `@/api/generated/model` and use `.options` to iterate values. Inline `Literal` fields do not get named schemas — use a `StrEnum` on the backend if the frontend needs to iterate the values.

**Flat response types**: `httpClient: 'axios'` in the config means hooks return the data directly. The response is `AgentResponse`, not `{ data: AgentResponse, status: 200 }`. All `setQueryData`/`getQueryData` calls use the flat type — no `.data` unwrapping.

**Configuration**:

```ts
// orval.config.ts
import { defineConfig } from 'orval'

export default defineConfig({
  apprise: {
    input: { target: 'http://localhost:8000/openapi.json' },
    output: {
      mode: 'tags-split',
      target: 'src/api/generated',
      schemas: { type: 'zod', path: 'src/api/generated/model' },
      client: 'react-query',
      httpClient: 'axios',
      formatter: 'prettier',
      override: {
        mutator: { path: 'src/api/client.ts', name: 'customInstance' },
        query: {
          useInfinite: false,
          signal: true,
          useInvalidate: true,
          useGetQueryData: true,
          useSetQueryData: true,
        },
      },
    },
    hooks: {
      afterAllFilesWrite: {
        command: 'node scripts/inject-zod-validation.mjs && bunx prettier --write src/api/generated',
        injectGeneratedDirsAndFiles: false,
      },
    },
  },
})
```

`mode: 'tags-split'` produces one file per FastAPI router tag. `afterAllFilesWrite` runs the injection script automatically after every generation — no manual step.

**The injection script** (`scripts/inject-zod-validation.mjs`) promotes `import type { Foo }` to value imports and injects the Zod schema as a third argument to every `customInstance<Foo>(...)` call. For array responses it wraps the schema: `z.array(AgentResponse)`. This is the correct pattern for Orval v8 with a custom mutator — the native `runtimeValidation: true` option does not work across config entries with a custom mutator.

**The custom fetcher**: All HTTP goes through `customInstance`. This is the only place the Axios instance is configured — base URL, auth interceptors, error normalisation. Clerk token injection is handled by `AxiosAuthSync` (a render-null component in `Providers`) that registers an Axios interceptor tied to the active Clerk session.

```ts
// src/api/client.ts
import Axios, { type AxiosRequestConfig } from 'axios'
import type { ZodType } from 'zod'

export const AXIOS_INSTANCE = Axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
})

export const customInstance = async <T>(
  config: AxiosRequestConfig,
  _options?: unknown,
  schema?: ZodType,
): Promise<T> => {
  const res = await AXIOS_INSTANCE.request<T>(config)
  const data = schema ? schema.parse(res.data) : res.data
  return data as T
}
```

**Workflow**:

```bash
# After any backend schema change:
bun run orval          # regenerate the API client
bun run tsc --noEmit   # type-check — errors indicate broken contracts
```

Both commands run as required CI steps on every pull request. A PR that changes FastAPI Pydantic models without regenerating the frontend client will fail type-checking in CI before it can be merged.

**Generated files are committed to git.** This is intentional. It allows CI to type-check without requiring a live API server, and gives reviewers visibility into what changed in the contract when a backend PR lands.

---

### Axios

Used exclusively through Orval's custom fetcher. Components never import Axios directly. Its sole purpose is to provide a centralisable HTTP client that all generated hooks share — base URL, request interceptors for auth, response interceptors for error normalisation. Changes to auth or the base URL are made once in `src/api/client.ts` and all hooks pick them up.

---

## State Management

### TanStack Query v5

**What it is**: A library for managing asynchronous server state in React. It handles caching, background refetching, stale/fresh state tracking, loading and error states, and cache invalidation.

**Why it is the correct tool**: The Apprise dashboard displays data that lives in Postgres and changes over time — agent skill scores, task completion states, Gini coefficients, influence snapshots. This data is not UI state. It is server state, and managing it in Zustand or Context leads to manual cache management, inconsistent loading states, and stale data bugs. TanStack Query was built specifically for this separation.

**Global configuration**:

```tsx
// src/app/providers.tsx
'use client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { useState } from 'react'

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,          // data stays fresh for 30 seconds
            refetchOnWindowFocus: true,  // background refresh when user returns to tab
          },
        },
      })
  )

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  )
}
```

`staleTime: 30_000` prevents redundant API calls during rapid navigation between workspace sub-routes. Data is refetched in the background when it becomes stale, not on every component mount.

**The WebSocket integration — the critical pattern**: The `useWorkspaceStream` hook maintains a persistent WebSocket connection. When an event arrives, it writes into the TanStack Query cache via `invalidateQueries` or `setQueryData`. Dashboard components always read from the TanStack Query cache — they never know whether an update came from an initial HTTP fetch or a live WebSocket push. The cache is the single source of truth.

```ts
// setQueryData applies an immediate update with no round trip — use only when
// the event carries the complete new state, e.g. the initial snapshot sent on
// subscribe
queryClient.setQueryData(
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey(workspaceId),
  initEvent.agents,
)

// invalidateQueries triggers a background refetch — use for delta events,
// where the message carries only what changed, not the full new state
queryClient.invalidateQueries({
  queryKey: getGetAgentWorkspacesWorkspaceIdAgentsAgentIdGetQueryKey(workspaceId, agentId),
})
```

Use `setQueryData` only for the initial snapshot (`init`) — it's the one event that carries complete state, so an immediate local write is correct and avoids a redundant refetch of data the message already contains. Use `invalidateQueries` for everything else — task completion, task executing, and skill updates all carry deltas or bare identifiers, not full state, so the server's authoritative response is what dashboard components need. This also keeps the dashboard correct after a reconnect or a missed publication: a delta event that arrived while disconnected is never silently lost, since the next `invalidateQueries` call re-fetches current server state rather than replaying a stale partial merge.

**Query key conventions**: Keys are generated by Orval — each hook exports a `get<HookName>QueryKey` factory. Always use these factories for `invalidateQueries` rather than hand-writing key arrays. This ensures cache invalidation stays in sync with the generated hooks as the API evolves.

```ts
import { getListTasksWorkspacesWorkspaceIdTasksGetQueryKey } from '@/api/generated/tasks/tasks'
import { getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey } from '@/api/generated/agents/agents'

// Correct — uses the Orval-generated factory
queryClient.invalidateQueries({
  queryKey: getListTasksWorkspacesWorkspaceIdTasksGetQueryKey(workspaceId),
})

// Wrong — hand-written key that can drift from the generated hook
queryClient.invalidateQueries({ queryKey: ['workspaces', workspaceId, 'tasks'] })
```

In Phase 2, artifact and tool registry queries follow the same pattern — use the Orval-generated key factory from the relevant generated file.

---

### Zustand

**What it manages**: UI-only state — state that exists in the interface but has no representation in the database.

- Which agent detail panel is open and which agent it is showing
- Task board view mode (list vs kanban)
- Active workspace ID for components that need it outside of URL params
- Any other ephemeral UI configuration

**What it does not manage**: Anything that lives in the database. Agent skills, task states, metrics, workspace configuration — all of that belongs in TanStack Query. If you find yourself putting API response data into Zustand, move it to TanStack Query.

```ts
// src/stores/workspace.ts
import { create } from 'zustand'

interface WorkspaceStore {
  selectedAgentId: string | null
  agentPanelOpen: boolean
  taskBoardView: 'list' | 'kanban'
  setSelectedAgent: (id: string | null) => void
  closeAgentPanel: () => void
  setTaskBoardView: (view: 'list' | 'kanban') => void
}

export const useWorkspaceStore = create<WorkspaceStore>((set) => ({
  selectedAgentId: null,
  agentPanelOpen: false,
  taskBoardView: 'list',
  setSelectedAgent: (id) => set({ selectedAgentId: id, agentPanelOpen: !!id }),
  closeAgentPanel: () => set({ selectedAgentId: null, agentPanelOpen: false }),
  setTaskBoardView: (view) => set({ taskBoardView: view }),
}))
```

Stores live in `src/stores/`, one file per domain. Keep stores small and domain-scoped.

---

## Type Safety and Validation

### Zod

**What it is**: A TypeScript-first schema declaration and runtime validation library. Defines the shape of data and validates it at runtime.

**Two distinct jobs in this codebase**:

**Job 1 — REST response validation (via Orval)**: Orval generates Zod schemas for every named API type. The barrel (`model/index.ts`) exports only `.zod.ts` files — these are both the runtime validators and the TypeScript type source. Every generated hook passes the Zod schema to `customInstance` as a third argument; `customInstance` calls `schema.parse(res.data)` before returning. A shape mismatch throws at the HTTP boundary with a descriptive Zod error, not silently deep in the UI.

Response types are flat — `AgentResponse` not `{ data: AgentResponse, status: 200 }`. Never unwrap `.data` from query results.

**Job 2 — WebSocket event validation (manual)**: Orval does not cover the WebSocket protocol. Every event type published by the backend to the stream endpoint requires a manually written Zod schema. These live in `src/hooks/useWorkspaceStream.ts`.

```ts
// src/hooks/useWorkspaceStream.ts
import { z } from 'zod'

const TaskCompletedEvent = z.object({
  type: z.literal('task.completed'),
  task_id: z.string(),
  agent_id: z.string(),
  quality_score: z.number().min(0).max(1),
})

const TaskExecutingEvent = z.object({
  type: z.literal('task.executing'),
  task_id: z.string(),
  agent_id: z.string(),
})

const AgentSkillUpdatedEvent = z.object({
  type: z.literal('agent.skill_updated'),
  agent_id: z.string(),
  skill_deltas: z.record(z.string(), z.number()),
  new_influence: z.number(),
})

const EmergenceDetectedEvent = z.object({
  type: z.literal('emergence.detected'),
  gini_coefficient: z.number(),
  hub_agent_id: z.string(),
})

export const WorkspaceEvent = z.discriminatedUnion('type', [
  TaskCompletedEvent,
  TaskExecutingEvent,
  AgentSkillUpdatedEvent,
  EmergenceDetectedEvent,
])

export type WorkspaceEvent = z.infer<typeof WorkspaceEvent>
```

`discriminatedUnion` on the `type` field means TypeScript will exhaustiveness-check switch statements over event types — adding a new event type to the union without handling it in the switch is a compile error, not a runtime omission.

Every incoming WebSocket message goes through `WorkspaceEvent.safeParse()` before it touches the query cache. A malformed event is silently discarded at the boundary. When a new event type is added to the backend, add its schema to the union — the switch statement will then surface anywhere that needs updating.

---

## UI Layer

### Tailwind CSS v4

The project uses Tailwind v4 throughout. Since we build our own component implementations rather than pulling from a third-party component library that assumes v3, there are no compatibility constraints. Tailwind v4's CSS-first configuration model (config in the main CSS file, not a separate `tailwind.config.js`) is cleaner for a custom component system.

```css
/* src/app/globals.css */
@import "tailwindcss";

:root {
  --background: #0a0a0f;
  --foreground: #ededed;
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-brand-primary: oklch(65% 0.2 165);
  --color-brand-accent: oklch(70% 0.15 280);
  --color-brand-highlight: oklch(72% 0.18 45);
  --font-sans: var(--font-inter);
  --font-mono: var(--font-jetbrains);
}
```

`@theme inline` (v4 syntax) inlines CSS variable references rather than resolving them at parse time, which is required for runtime theming. Note the use of `var(--font-inter)` / `var(--font-jetbrains)` — these are injected by Next.js `next/font` at the `<html>` element as CSS variables.

Custom design tokens are defined in `@theme` and are then available as Tailwind utilities throughout the codebase (`text-brand-primary`, `bg-brand-accent`, and so on).

---

### Radix UI

**What it is**: A collection of unstyled, accessible React component primitives.

**Why it is used**: Building custom-styled components does not mean building from scratch at the behaviour level. Accessibility is non-trivial — keyboard navigation, ARIA roles, focus management, screen reader announcements, and correct semantics for modals, dropdowns, tooltips, and tabs require substantial effort to implement correctly and consistently. Radix handles all of this. We provide visual styling via Tailwind; Radix provides the behaviour and accessibility contract.

This is exactly the model that shadcn/ui uses under the hood (Radix primitives + Tailwind styling). By using Radix directly, we own the full implementation without being tied to shadcn's design decisions or upgrade cycle.

Radix packages are installed individually as needed rather than as a single bundle:

```bash
bun add @radix-ui/react-dialog          # agent detail panel, confirmation modals
bun add @radix-ui/react-dropdown-menu   # workspace switcher, action menus
bun add @radix-ui/react-tooltip         # metric explanations, icon labels
bun add @radix-ui/react-tabs            # agent detail tabs (skills / memory / history)
bun add @radix-ui/react-select          # task type filter, tool category filter (Phase 2)
bun add @radix-ui/react-popover         # filter panels, date pickers
```

Install only the primitives the current build phase requires. Radix packages are small and tree-shakeable — there is no reason to install the full set upfront.

---

### Lucide React

Icon library. Consistently styled, tree-shakeable, React-native. Import only the icons used in the current file.

```tsx
import { Activity, Brain, Zap, GitBranch, AlertTriangle } from 'lucide-react'
```

No other icon library. No inline SVGs for UI icons.

---

### Framer Motion

**What it manages**: Component-level transitions across the dashboard — the agent detail panel sliding in from the right, task cards transitioning between status states, skill delta flashes when an agent's score updates after a completed task, emergence alert banners animating in.

**Scope boundary**: Framer Motion handles React component transitions only. It does not handle chart animations (delegated to the charting library) or graph animations (delegated to ReactFlow). Do not reach for Framer Motion for anything that a CSS transition would cover adequately — Framer Motion adds bundle weight and should be used where the animation logic is genuinely stateful or physics-based.

```tsx
// Agent detail panel — slides in from the right
import { AnimatePresence, motion } from 'framer-motion'

<AnimatePresence>
  {agentPanelOpen && (
    <motion.aside
      initial={{ x: '100%' }}
      animate={{ x: 0 }}
      exit={{ x: '100%' }}
      transition={{ type: 'spring', damping: 30, stiffness: 300 }}
      className="fixed right-0 top-0 h-full w-[480px] border-l bg-background"
    >
      <AgentDetailPanel agentId={selectedAgentId} />
    </motion.aside>
  )}
</AnimatePresence>
```

`AnimatePresence` should be placed at the layout level when wrapping route transitions, not re-instantiated inside individual leaf components. All components using Framer Motion are inside the `'use client'` boundary — they will be already, given the workspace layout.

---

## Data Visualisation

**Status: undecided.** The charting library for Apprise's research and product metrics has not been finalised. This section will be updated when the decision is made.

Candidates under consideration include Observable Plot (well-suited to scientific and analytical data, non-React-native) and Recharts (React-native, compositional). The decision will primarily be driven by the specific rendering requirements of the Gini coefficient timeline, skill divergence charts, and emergence event markers.

**What is already decided**: Any chart library will be integrated through a `usePlot` hook pattern that wraps the container in a `ResizeObserver`. This is required to handle React's concurrent renderer correctly — charts that calculate their dimensions at mount time can receive a zero-width container if they mount before the layout is stable. The `ResizeObserver` defers the mount until the container has a stable non-zero width.

```ts
// src/hooks/usePlot.ts — base pattern for any imperative chart library
import { useEffect, useRef } from 'react'

export function usePlot<T>(
  data: T[],
  render: (container: HTMLDivElement, data: T[], width: number) => void,
  deps: React.DependencyList = []
) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return

    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width
      if (!width || !ref.current) return
      render(ref.current, data, width)
    })

    observer.observe(ref.current)
    return () => observer.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, ...deps])

  return ref
}
```

When the charting library is chosen, chart components are built on top of this hook and nowhere else. This means switching the underlying library only requires changing `usePlot` implementations, not updating individual chart components.

---

## Graph Visualisation

### ReactFlow (`@xyflow/react`)

**What it is**: A React library for building interactive node and edge graph UIs — diagrams where nodes are connected by directed edges, with support for custom node types, interactive pan/zoom, and programmatic layout.

**Why it is in the stack from day one**: Phase 2's artefact operation model produces a directed acyclic graph of operations connected by `depends_on` relationships. An artefact representing a software feature decomposes into operations like `implement → test → review → document`, where each depends on the previous completing. This dependency graph needs to be rendered interactively — showing which operations are pending, in progress, complete, or blocked, and which agents are assigned to each node.

ReactFlow is the correct tool for this. It handles node/edge layout, zoom/pan, custom node rendering, and interactive selection. Nothing else in the stack handles arbitrary graph topology.

**Phase 3 application**: The same component model extends to agent fleet topology — which agents are acting as coordinators (the emergent leadership signal), how work is flowing through the physical fleet, and which agents are currently executing. The artefact dependency graph component and the fleet topology component share the same ReactFlow-based infrastructure.

**Scope boundary**: ReactFlow renders node/edge graph topology. It is not a charting library and should not be used for time-series data or metrics visualisation.

---

## Code Editor

### Monaco Editor (`@monaco-editor/react`)

**What it is**: Microsoft's VS Code editor engine wrapped as a React component.

**Phase 2 — Tool builder**: When customers register a custom tool by providing a Python function implementation inline, they write and edit the code in a Monaco Editor instance within the tool builder form. Monaco provides syntax highlighting, bracket matching, and basic Python IntelliSense, giving customers a familiar editing environment that matches their own tooling.

**Phase 2 — Artefact viewer**: When the artefact viewer displays the output of a coding task — a source file, a test file, a configuration — Monaco renders it with full syntax highlighting in read-only mode.

```tsx
import Editor from '@monaco-editor/react'

<Editor
  height="400px"
  language="python"
  value={toolImplementation}
  onChange={(value) => setToolImplementation(value ?? '')}
  options={{
    minimap: { enabled: false },
    fontSize: 13,
    fontFamily: 'JetBrains Mono, monospace',
    readOnly: isViewMode,
    scrollBeyondLastLine: false,
  }}
  theme="vs-dark"
/>
```

Monaco is loaded lazily by the React wrapper using dynamic imports — it does not contribute to the initial dashboard bundle. The first render of a component containing Monaco triggers a deferred load.

---

## Utilities

### date-fns

Date formatting and manipulation. Used for formatting timestamps on emergence events and task completion records, computing relative time strings for agent last-active displays, and binning time-series data into intervals for chart rendering.

```ts
import { format, formatDistanceToNow, startOfHour, eachHourOfInterval } from 'date-fns'

format(new Date(task.completed_at), 'HH:mm:ss')
formatDistanceToNow(new Date(agent.updated_at), { addSuffix: true })
```

`date-fns` is fully tree-shakeable — only the imported functions appear in the bundle. No configuration required.

---

## Key Architectural Patterns

### WebSocket → TanStack Query Integration

The worker publishes typed dashboard events to Centrifugo (a dedicated real-time
messaging server — migrated off a hand-rolled Redis Pub/Sub + FastAPI WebSocket
route, which didn't scale past one Redis connection per workspace). The browser
connects to Centrifugo directly via the `centrifuge` client SDK, authenticated
via a connect/subscribe proxy callback into the API process
(`backend/api/api/routers/centrifugo_proxy.py`) rather than a bearer token on
the socket itself. The `useWorkspaceStream` hook maintains this connection for
the full duration of the workspace session; the illustrative snippet below is
simplified to show the event-dispatch shape, not the exact transport wiring —
see the actual hook for that.

```ts
// src/hooks/workspace/useWorkspaceStream.ts
export function useWorkspaceStream(workspaceId: string) {
  const queryClient = useQueryClient()

  useEffect(() => {
    const centrifuge = new Centrifuge(process.env.NEXT_PUBLIC_CENTRIFUGO_URL, {
      getData: async () => ({ clerkToken: await getToken() }),
    })
    const sub = centrifuge.newSubscription(`workspace:${workspaceId}:events`)

    sub.on('publication', (ctx: { data: unknown }) => {
      const result = WorkspaceEvent.safeParse(ctx.data)
      if (!result.success) return

      const e = result.data

      switch (e.type) {
        case 'task.completed':
        case 'task.executing':
          void queryClient.invalidateQueries({
            queryKey: getListTasksWorkspacesWorkspaceIdTasksGetQueryKey(workspaceId),
          })
          break
        case 'agent.skill_updated':
          void queryClient.invalidateQueries({
            queryKey: getGetAgentWorkspacesWorkspaceIdAgentsAgentIdGetQueryKey(workspaceId, e.agent_id),
          })
          void queryClient.invalidateQueries({
            queryKey: getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey(workspaceId),
          })
          break
        case 'emergence.detected':
          useToastStore.getState().toast({ title: 'Emergence detected', variant: 'default' })
          break
      }
    })

    sub.subscribe()
    centrifuge.connect()

    return () => centrifuge.disconnect()
  }, [workspaceId, queryClient])
}
```

All cache invalidation uses Orval-generated key factories. `invalidateQueries` is preferred over `setQueryData` for agent skill updates — the event carries deltas, not the full new state, so the authoritative source is the server.

The hook is currently mounted in `AppHeader.tsx` (a known drift from the original design intent of mounting it in `app/workspaces/[id]/layout.tsx` so it'd survive navigation without remounting — tracked separately, not fixed by the Centrifugo migration).

---

### Orval Regeneration Workflow

When the FastAPI backend adds, removes, or modifies an endpoint or model:

```bash
# 1. Ensure the backend is running with the updated schema
# 2. Regenerate the API client
bun run orval

# 3. Identify contract breaks
bun run tsc --noEmit

# 4. Fix TypeScript errors — each one marks a location where the contract changed
# 5. Commit generated files alongside the component changes that consume them
```

Generated files in `src/api/generated/` are committed to git. This allows CI to run `tsc --noEmit` without a live API server running. The CI pipeline treats a type error from schema drift as a blocking failure.

---

### Environment Variables

```bash
# .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000                              # FastAPI base URL (browser-accessible)
NEXT_PUBLIC_CENTRIFUGO_URL=ws://localhost:8001/connection/websocket    # Centrifugo WS endpoint (browser-accessible)
API_URL=http://localhost:8000               # Server-side only — used in RSC prefetching
```

`NEXT_PUBLIC_` variables are inlined into the browser bundle at build time. `API_URL` (no prefix) is only available in server-side code — server components, route handlers, and middleware. Never put secrets or credentials in `NEXT_PUBLIC_` variables.

---

## Install Reference

```bash
# Scaffold
bun create next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --no-import-alias
cd frontend

# Core
bun add @tanstack/react-query @tanstack/react-query-devtools zustand zod axios date-fns

# UI layer
bun add @radix-ui/react-dialog @radix-ui/react-dropdown-menu @radix-ui/react-tooltip @radix-ui/react-tabs lucide-react framer-motion

# Visualisation
bun add @xyflow/react @monaco-editor/react
# charting library TBD

# Dev
bun add --dev orval
```

---

## Adding a New Feature Checklist

When adding a new dashboard feature or page:

1. **Check if the backend endpoint exists.** If it does, run `bun run orval` — the hook is already generated.
2. **Decide where the data lives.** Server state (anything from the API or WebSocket) → TanStack Query. UI-only state → Zustand.
3. **Add WebSocket event handlers** if the feature responds to live events. Add the Zod schema to the `WorkspaceEvent` union first.
4. **Place the component inside the workspace layout subtree** (`app/workspaces/[id]/`). It inherits the client boundary and the WebSocket connection automatically.
5. **Run `bun run tsc --noEmit`** before opening a PR. Do not rely on the editor alone.
