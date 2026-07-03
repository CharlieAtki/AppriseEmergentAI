'use client'

import Link from 'next/link'
import { motion } from 'framer-motion'
import { Pencil, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import type { WorkspaceResponse } from '@/api/generated/model'
import { Badge } from '@/components/ui/Badge'
import { WorkspaceAvatar } from './WorkspaceAvatar'
import { cardHover } from '@/lib/motion'
import { EditWorkspaceDialog } from './EditWorkspaceDialog'
import { DeleteWorkspaceDialog } from './DeleteWorkspaceDialog'
import { WorkspaceInfoPopover } from './WorkspaceInfoPopover'
import { useWorkspaceDelete } from '@/hooks/workspace/useWorkspaceDelete'

interface WorkspaceCardProps {
  workspace: WorkspaceResponse
  orgId: string
  view: 'grid' | 'list'
}

export function WorkspaceCard({ workspace, orgId, view }: WorkspaceCardProps) {
  const [editOpen, setEditOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const { deleteWorkspace } = useWorkspaceDelete()

  const createdAt = workspace.created_at
    ? formatDistanceToNow(new Date(workspace.created_at), { addSuffix: true })
    : null

  function handleConfirmDelete() {
    setDeleteOpen(false)
    deleteWorkspace(workspace)
  }

  const actions = (
    <div className="flex items-center gap-0.5">
      <WorkspaceInfoPopover workspace={workspace} />
      <button
        onClick={() => setEditOpen(true)}
        aria-label="Edit workspace"
        className="rounded-md p-1.5 text-muted transition-colors hover:bg-hover hover:text-foreground"
      >
        <Pencil size={14} />
      </button>
      <button
        onClick={() => setDeleteOpen(true)}
        aria-label="Delete workspace"
        className="rounded-md p-1.5 text-error transition-colors hover:bg-error/10"
      >
        <Trash2 size={14} />
      </button>
    </div>
  )

  const dialogs = (
    <>
      <EditWorkspaceDialog workspace={workspace} open={editOpen} onOpenChange={setEditOpen} />
      <DeleteWorkspaceDialog
        workspace={workspace}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onConfirm={handleConfirmDelete}
      />
    </>
  )

  if (view === 'list') {
    return (
      <>
        <motion.div
          whileHover={cardHover}
          className="workspace-card group flex items-center gap-4 rounded-lg border border-border bg-surface px-4 py-3 focus-within:ring-2 focus-within:ring-brand-primary"
        >
          <WorkspaceAvatar name={workspace.name} size="md" />

          {/* Name + subtitle */}
          <Link
            href={`/orgs/${orgId}/workspaces/${workspace.id}`}
            className="flex min-w-0 flex-1 flex-col focus-visible:outline-none"
          >
            <span className="text-body font-semibold text-foreground truncate">{workspace.name}</span>
            {createdAt && (
              <span className="text-caption text-muted">Created {createdAt}</span>
            )}
          </Link>

          {/* Stats + badge + icon actions */}
          <div className="flex items-center gap-3 shrink-0">
            <span className="text-caption text-muted hidden sm:block">
              {workspace.agent_count ?? 0} agent{(workspace.agent_count ?? 0) !== 1 ? 's' : ''}
            </span>
            <Badge status={workspace.status} />
            <div className="flex items-center gap-0.5">
              <WorkspaceInfoPopover workspace={workspace} />
              <button
                onClick={() => setEditOpen(true)}
                aria-label="Edit workspace"
                className="rounded-md p-1.5 text-muted transition-colors hover:bg-hover hover:text-foreground"
              >
                <Pencil size={14} />
              </button>
              <button
                onClick={() => setDeleteOpen(true)}
                aria-label="Delete workspace"
                className="rounded-md p-1.5 text-error transition-colors hover:bg-error/10"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        </motion.div>
        {dialogs}
      </>
    )
  }

  return (
    <>
      <motion.div
        whileHover={cardHover}
        className="workspace-card group flex flex-col rounded-lg border border-border bg-surface focus-within:ring-2 focus-within:ring-brand-primary"
      >
        <Link
          href={`/orgs/${orgId}/workspaces/${workspace.id}`}
          className="flex flex-col gap-3 p-5 pb-4 focus-visible:outline-none"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <WorkspaceAvatar name={workspace.name} size="md" />
              <h2 className="text-title font-semibold text-foreground truncate">
                {workspace.name}
              </h2>
            </div>
            <Badge status={workspace.status} />
          </div>
          <p className="text-caption text-muted">
            {workspace.agent_count ?? 0} agent{(workspace.agent_count ?? 0) !== 1 ? 's' : ''}
            {createdAt ? ` · Created ${createdAt}` : ''}
          </p>
        </Link>

        <div className="flex items-center gap-1 border-t border-border-subtle px-3 py-2">
          {actions}
        </div>
      </motion.div>
      {dialogs}
    </>
  )
}
