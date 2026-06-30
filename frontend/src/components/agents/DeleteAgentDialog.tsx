'use client'

import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { IconDelete } from '@/lib/icons'
import type { AgentResponse } from '@/api/generated/fastAPI.schemas'

interface DeleteAgentDialogProps {
  agent: AgentResponse
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
}

export function DeleteAgentDialog({ agent, open, onOpenChange, onConfirm }: DeleteAgentDialogProps) {
  return (
    <AlertDialog.Root open={open} onOpenChange={onOpenChange}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="dialog-overlay fixed inset-0 z-50 bg-background/60 backdrop-blur-sm" />
        <AlertDialog.Content className="dialog-content fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-error/10">
              <IconDelete size={18} className="text-error" />
            </div>
            <div className="min-w-0">
              <AlertDialog.Title className="text-title font-semibold text-foreground">
                Delete agent
              </AlertDialog.Title>
              <AlertDialog.Description className="mt-1 text-body text-muted">
                <span className="font-medium text-secondary">{agent.name}</span> will be
                deleted. You'll have 5 seconds to undo.
              </AlertDialog.Description>
            </div>
          </div>

          <div className="mt-6 flex justify-end gap-2">
            <AlertDialog.Cancel asChild>
              <button
                type="button"
                className="rounded-lg px-4 py-2 text-body text-muted transition-colors hover:text-foreground"
              >
                Cancel
              </button>
            </AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <button
                onClick={onConfirm}
                className="rounded-lg bg-error px-4 py-2 text-body font-medium text-white transition-colors hover:opacity-90"
              >
                Delete
              </button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
