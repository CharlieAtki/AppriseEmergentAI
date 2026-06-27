import type { WorkspaceResponse } from '@/api/generated/fastAPI.schemas'
import { WorkspaceCard } from './WorkspaceCard'

interface WorkspaceGridProps {
  workspaces: WorkspaceResponse[]
  orgId: string
}

export function WorkspaceGrid({ workspaces, orgId }: WorkspaceGridProps) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {workspaces.map((workspace) => (
        <WorkspaceCard key={workspace.id} workspace={workspace} orgId={orgId} />
      ))}
    </div>
  )
}
