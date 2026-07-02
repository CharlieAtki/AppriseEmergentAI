'use client'

import { Plus } from 'lucide-react'
import Link from 'next/link'
import { useParams, usePathname } from 'next/navigation'
import { useState } from 'react'
import { useListWorkspacesWorkspacesGet } from '@/api/generated/workspaces/workspaces'
import { WorkspaceAvatar } from '@/components/workspaces/WorkspaceAvatar'
import { CreateWorkspaceDialog } from '@/components/workspaces/CreateWorkspaceDialog'

interface WorkspaceSidebarSectionProps {
  orgId: string
}

export function WorkspaceSidebarSection({ orgId }: WorkspaceSidebarSectionProps) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const params = useParams<{ workspaceId?: string }>()
  const pathname = usePathname()
  const { data } = useListWorkspacesWorkspacesGet()
  // FAVOURITES STUB: When implemented, favourited workspace IDs will be read from a
  // Zustand store persisted to localStorage. Favourited workspaces render first with a
  // visual separator before the rest. See stores/workspaceFavourites.ts (to be created).
  const workspaces = data?.data ?? []

  const currentSegment = (() => {
    const { workspaceId } = params
    if (!workspaceId) return null
    const base = `/orgs/${orgId}/workspaces/${workspaceId}`
    const rest = pathname.startsWith(base) ? pathname.slice(base.length) : ''
    return rest.replace(/^\//, '').split('/')[0] || null
  })()

  return (
    <>
      <div>
        <p className="mb-1 px-2 text-label font-semibold uppercase tracking-architectural text-muted">
          Workspaces
        </p>
        <ul className="space-y-0.5">
          {workspaces.map((ws) => {
            const isActive = params.workspaceId === ws.id
            const isOnline = ws.status === 'active'
            return (
              <li key={ws.id}>
                <Link
                  href={`/orgs/${orgId}/workspaces/${ws.id}${currentSegment ? `/${currentSegment}` : ''}`}
                  className={`flex items-center gap-2 py-1.5 text-body transition-colors ${
                    isActive
                      ? 'rounded-r-md border-l-2 border-brand-primary bg-brand-primary/10 pl-[6px] pr-2 font-medium text-brand-primary'
                      : 'rounded-md px-2 text-secondary hover:bg-elevated hover:text-foreground'
                  }`}
                >
                  <WorkspaceAvatar name={ws.name} size="sm" />
                  <span className="flex-1 truncate">{ws.name}</span>
                  <span
                    aria-hidden="true"
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${isOnline ? 'bg-success' : 'bg-muted'}`}
                  />
                </Link>
              </li>
            )
          })}
          <li>
            <button
              onClick={() => setDialogOpen(true)}
              className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-body text-muted transition-colors hover:bg-elevated hover:text-foreground"
            >
              <Plus size={13} className="shrink-0" />
              New workspace
            </button>
          </li>
        </ul>
      </div>

      <CreateWorkspaceDialog orgId={orgId} open={dialogOpen} onOpenChange={setDialogOpen} />
    </>
  )
}
