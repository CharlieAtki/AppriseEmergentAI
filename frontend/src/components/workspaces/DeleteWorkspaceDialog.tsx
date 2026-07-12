'use client'

import { ConfirmDeleteDialog } from '@/components/ui/ConfirmDeleteDialog'
import type { WorkspaceResponse } from '@/api/generated/model'

interface DeleteWorkspaceDialogProps {
  workspace: WorkspaceResponse
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
}

export function DeleteWorkspaceDialog({ workspace, open, onOpenChange, onConfirm }: DeleteWorkspaceDialogProps) {
  return (
    <ConfirmDeleteDialog
      open={open}
      onOpenChange={onOpenChange}
      onConfirm={onConfirm}
      title="Delete workspace"
      description={
        <>
          <span className="font-medium text-secondary">{workspace.name}</span> will be deleted. You'll have 5
          seconds to undo.
        </>
      }
    />
  )
}
