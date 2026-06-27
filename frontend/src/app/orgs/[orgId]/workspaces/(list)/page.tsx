import { WorkspaceList } from '../_components/WorkspaceList'

// No SSR prefetch: listWorkspacesWorkspacesGet() routes through customInstance → AXIOS_INSTANCE,
// which has no Authorization header server-side (AxiosAuthSync is client-only). A HydrationBoundary
// prefetch requires a raw fetch() with a server-side Clerk token — deferred to a future iteration.
export default function WorkspacesPage() {
  return (
    <main className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">Workspaces</h1>
        <p className="mt-1 text-sm text-muted">Select a workspace to open its dashboard.</p>
      </div>
      <WorkspaceList />
    </main>
  )
}
