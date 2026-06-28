'use client'

import Link from 'next/link'
import { motion } from 'framer-motion'
import { Pencil, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import type { WorkspaceResponse } from '@/api/generated/fastAPI.schemas'
import { Badge } from '@/components/ui/Badge'
import { cardHover } from '@/lib/motion'
import { EditWorkspaceDialog } from './EditWorkspaceDialog'
import { DeleteWorkspaceDialog } from './DeleteWorkspaceDialog'
import { WorkspaceInfoPopover } from './WorkspaceInfoPopover'
import { useWorkspaceDelete } from '@/hooks/useWorkspaceDelete'

interface WorkspaceCardProps {
  workspace: WorkspaceResponse
  orgId: string
}

export function WorkspaceCard({ workspace, orgId }: WorkspaceCardProps) {
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

  return (
    <>
      <motion.div
        whileHover={cardHover}
        className="workspace-card group flex flex-col rounded-lg border border-border bg-surface focus-within:ring-2 focus-within:ring-brand-primary"
      >
        <Link
          href={`/orgs/${orgId}/workspaces/${workspace.id}`}
          className="flex flex-col gap-4 p-6 pb-4 focus-visible:outline-none"
        >
          <div className="flex items-start justify-between gap-3">
            <h2 className="text-title font-semibold text-foreground group-hover:text-brand-primary transition-colors">
              {workspace.name}
            </h2>
            <Badge status={workspace.status} />
          </div>
          {createdAt && (
            <p className="text-caption text-muted">Created {createdAt}</p>
          )}
        </Link>

        <div className="flex items-center gap-1 border-t border-border-subtle px-4 py-2">
          <WorkspaceInfoPopover workspace={workspace} />
          <button
            onClick={() => setEditOpen(true)}
            aria-label="Edit workspace"
            className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted transition-colors hover:bg-hover hover:text-foreground"
          >
            <Pencil size={13} />
            Edit
          </button>
          <button
            onClick={() => setDeleteOpen(true)}
            aria-label="Delete workspace"
            className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted transition-colors hover:bg-hover hover:text-error"
          >
            <Trash2 size={13} />
            Delete
          </button>
        </div>
      </motion.div>

      <EditWorkspaceDialog
        workspace={workspace}
        open={editOpen}
        onOpenChange={setEditOpen}
      />
      <DeleteWorkspaceDialog
        workspace={workspace}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onConfirm={handleConfirmDelete}
      />
    </>
  )
}
