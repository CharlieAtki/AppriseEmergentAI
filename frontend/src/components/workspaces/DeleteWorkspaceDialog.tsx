'use client'

import * as Dialog from '@radix-ui/react-dialog'
import { X, Trash2 } from 'lucide-react'
import type { WorkspaceResponse } from '@/api/generated/fastAPI.schemas'

interface DeleteWorkspaceDialogProps {
  workspace: WorkspaceResponse
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
}

export function DeleteWorkspaceDialog({ workspace, open, onOpenChange, onConfirm }: DeleteWorkspaceDialogProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay fixed inset-0 bg-background/60 backdrop-blur-sm" />
        <Dialog.Content className="dialog-content fixed left-1/2 top-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-error/10">
              <Trash2 size={18} className="text-error" />
            </div>
            <div className="min-w-0">
              <Dialog.Title className="text-base font-semibold text-foreground">
                Delete workspace
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-muted">
                <span className="font-medium text-secondary">{workspace.name}</span> will be
                deleted. You'll have 5 seconds to undo.
              </Dialog.Description>
            </div>
          </div>

          <div className="mt-6 flex justify-end gap-2">
            <Dialog.Close asChild>
              <button
                type="button"
                className="rounded-lg px-4 py-2 text-sm text-muted transition-colors hover:text-foreground"
              >
                Cancel
              </button>
            </Dialog.Close>
            <button
              onClick={onConfirm}
              className="rounded-lg bg-error px-4 py-2 text-sm font-medium text-white transition-colors hover:opacity-90"
            >
              Delete
            </button>
          </div>

          <Dialog.Close asChild>
            <button
              className="absolute right-4 top-4 text-muted transition-colors hover:text-foreground"
              aria-label="Close"
            >
              <X size={16} />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
