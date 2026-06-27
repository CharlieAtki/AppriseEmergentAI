'use client'

import { useParams } from 'next/navigation'
import { useListWorkspacesWorkspacesGet } from '@/api/generated/workspaces/workspaces'
import { WorkspaceGrid } from '@/components/workspaces/WorkspaceGrid'

export function WorkspaceList() {
  const { orgId } = useParams<{ orgId: string }>()
  const { data, isPending, isError } = useListWorkspacesWorkspacesGet()

  if (isPending) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-36 animate-pulse rounded-lg bg-surface" />
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <p className="text-sm text-error">
        Failed to load workspaces. Please refresh the page.
      </p>
    )
  }

  const workspaces = data.data

  if (workspaces.length === 0) {
    return (
      <p className="text-sm text-muted">
        No workspaces yet. Create one to get started.
      </p>
    )
  }

  return <WorkspaceGrid workspaces={workspaces} orgId={orgId} />
}
