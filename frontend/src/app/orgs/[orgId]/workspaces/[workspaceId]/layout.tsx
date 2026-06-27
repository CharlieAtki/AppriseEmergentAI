'use client'

import { use } from 'react'
import { useGetWorkspaceWorkspacesWorkspaceIdGet } from '@/api/generated/workspaces/workspaces'
import { WorkspaceHeader } from '@/components/layout/WorkspaceHeader'
import { WorkspaceSidebar } from '@/components/layout/WorkspaceSidebar'
import { useWorkspaceStream } from '@/hooks/useWorkspaceStream'

export default function WorkspaceLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ orgId: string; workspaceId: string }>
}) {
  const { orgId, workspaceId } = use(params)
  const { connected } = useWorkspaceStream(workspaceId)
  const { data } = useGetWorkspaceWorkspacesWorkspaceIdGet(workspaceId)
  const workspaceName = data?.status === 200 ? data.data.name : workspaceId

  return (
    <div className="flex min-h-screen">
      <WorkspaceSidebar orgId={orgId} workspaceId={workspaceId} workspaceName={workspaceName} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <WorkspaceHeader connected={connected} />
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  )
}
