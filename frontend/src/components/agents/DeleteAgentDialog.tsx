'use client'

import { ConfirmDeleteDialog } from '@/components/ui/ConfirmDeleteDialog'
import type { AgentResponse } from '@/api/generated/model'

interface DeleteAgentDialogProps {
  agent: AgentResponse
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
}

export function DeleteAgentDialog({ agent, open, onOpenChange, onConfirm }: DeleteAgentDialogProps) {
  return (
    <ConfirmDeleteDialog
      open={open}
      onOpenChange={onOpenChange}
      onConfirm={onConfirm}
      title="Delete agent"
      description={
        <>
          <span className="font-medium text-secondary">{agent.name}</span> will be deleted. You'll have 5 seconds
          to undo.
        </>
      }
    />
  )
}
