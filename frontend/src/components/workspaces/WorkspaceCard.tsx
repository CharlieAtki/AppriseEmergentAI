import Link from 'next/link'
import { formatDistanceToNow } from 'date-fns'
import type { WorkspaceResponse } from '@/api/generated/fastAPI.schemas'
import { Badge } from '@/components/ui/Badge'

interface WorkspaceCardProps {
  workspace: WorkspaceResponse
  orgId: string
}

export function WorkspaceCard({ workspace, orgId }: WorkspaceCardProps) {
  const createdAt = workspace.created_at
    ? formatDistanceToNow(new Date(workspace.created_at), { addSuffix: true })
    : null

  return (
    <Link
      href={`/orgs/${orgId}/workspaces/${workspace.id}`}
      className="group flex flex-col gap-4 rounded-lg border border-border bg-surface p-6 transition-colors hover:bg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary"
    >
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-base font-medium text-foreground group-hover:text-brand-primary transition-colors">
          {workspace.name}
        </h2>
        <Badge status={workspace.status} />
      </div>
      {createdAt && (
        <p className="text-xs text-muted">Created {createdAt}</p>
      )}
    </Link>
  )
}
