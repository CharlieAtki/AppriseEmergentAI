'use client'

import * as Collapsible from '@radix-ui/react-collapsible'
import { ChevronRight, LayoutGrid, Plus } from 'lucide-react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useState } from 'react'
import { useListWorkspacesWorkspacesGet } from '@/api/generated/workspaces/workspaces'
import { CreateWorkspaceDialog } from '@/components/workspaces/CreateWorkspaceDialog'

interface WorkspaceSidebarSectionProps {
  orgId: string
}

export function WorkspaceSidebarSection({ orgId }: WorkspaceSidebarSectionProps) {
  const [open, setOpen] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const params = useParams<{ workspaceId?: string }>()
  const { data } = useListWorkspacesWorkspacesGet()
  const workspaces = data?.data ?? []

  return (
    <>
      <Collapsible.Root open={open} onOpenChange={setOpen}>
        <Collapsible.Trigger asChild>
          <button className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs font-semibold uppercase tracking-wide text-muted transition-colors hover:bg-elevated hover:text-foreground">
            <ChevronRight
              size={14}
              className={`shrink-0 transition-transform duration-150 ${open ? 'rotate-90' : ''}`}
            />
            <LayoutGrid size={14} className="shrink-0" />
            Workspaces
          </button>
        </Collapsible.Trigger>

        <Collapsible.Content className="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
          <ul className="ml-4 mt-1 space-y-0.5 border-l border-border-subtle pl-3">
            <li>
              <button
                onClick={() => setDialogOpen(true)}
                className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted transition-colors hover:bg-elevated hover:text-foreground"
              >
                <Plus size={13} className="shrink-0" />
                New workspace
              </button>
            </li>

            {workspaces.map((ws) => {
              const isActive = params.workspaceId === ws.id
              return (
                <li key={ws.id}>
                  <Link
                    href={`/orgs/${orgId}/workspaces/${ws.id}`}
                    className={`block truncate rounded-md px-2 py-1.5 text-sm transition-colors ${
                      isActive
                        ? 'bg-brand-primary/10 font-medium text-brand-primary'
                        : 'text-secondary hover:bg-elevated hover:text-foreground'
                    }`}
                  >
                    {ws.name}
                  </Link>
                </li>
              )
            })}
          </ul>
        </Collapsible.Content>
      </Collapsible.Root>

      <CreateWorkspaceDialog orgId={orgId} open={dialogOpen} onOpenChange={setDialogOpen} />
    </>
  )
}
