import { WorkspaceList } from '../_components/WorkspaceList'

// No SSR prefetch: listWorkspacesWorkspacesGet() routes through customInstance → AXIOS_INSTANCE,
// which has no Authorization header server-side (AxiosAuthSync is client-only). A HydrationBoundary
// prefetch requires a raw fetch() with a server-side Clerk token — deferred to a future iteration.
export default function WorkspacesPage() {
  return (
    <main className="p-8">
      <div className="max-w-[1440px] mx-auto">
        <WorkspaceList />
      </div>
    </main>
  )
}
