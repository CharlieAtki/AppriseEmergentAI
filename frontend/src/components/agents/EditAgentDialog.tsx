'use client'

import { Button } from '@/components/ui/button'

import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Field, FieldLabel, FieldError } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useUpdateAgentWorkspacesWorkspaceIdAgentsAgentIdPatch,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
} from '@/api/generated/agents/agents'
import { IconAgent } from '@/lib/icons'
import type { AgentResponse } from '@/api/generated/model'

interface EditAgentDialogProps {
  agent: AgentResponse
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function EditAgentDialog({ agent, open, onOpenChange }: EditAgentDialogProps) {
  const [name, setName] = useState(agent.name)
  const [submitted, setSubmitted] = useState(false)
  const queryClient = useQueryClient()
  const nameMissing = submitted && name.trim().length === 0

  useEffect(() => {
    if (open) {
      setName(agent.name)
      setSubmitted(false)
    }
  }, [open, agent.name])

  const { mutate, isPending } = useUpdateAgentWorkspacesWorkspaceIdAgentsAgentIdPatch({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({
          queryKey: getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey(agent.workspace_id),
        })
        onOpenChange(false)
      },
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-primary/15 text-brand-primary">
            <IconAgent size={18} />
          </div>
          <div>
            <DialogTitle className="text-title font-semibold text-foreground">
              Edit agent
            </DialogTitle>
            <DialogDescription className="mt-0.5 text-body text-muted">
              Update the agent's name.
            </DialogDescription>
          </div>
        </div>

        <form
          className="mt-5 space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            setSubmitted(true)
            const trimmed = name.trim()
            if (!trimmed) return
            mutate({ workspaceId: agent.workspace_id, agentId: agent.id, data: { name: trimmed } })
          }}
        >
          <Field data-invalid={nameMissing || undefined}>
            <FieldLabel htmlFor="edit-agent-name" className="text-label font-medium text-secondary">
              Name
            </FieldLabel>
            <Input
              id="edit-agent-name"
              autoFocus
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={nameMissing}
              className="rounded-lg border-border bg-elevated px-3 py-2 text-body text-foreground placeholder:text-muted focus-visible:border-brand-primary focus-visible:ring-brand-primary"
            />
            {nameMissing && <FieldError>Name is required.</FieldError>}
          </Field>

          <div className="flex justify-end gap-2 pt-1">
            <Button
              type="button"
              onClick={() => onOpenChange(false)}
              className="rounded-lg px-4 py-2 text-body text-muted transition-colors hover:text-foreground"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isPending}
              className="rounded-lg bg-brand-primary px-4 py-2 text-body font-medium text-background transition-colors hover:bg-brand-hover disabled:opacity-50"
            >
              {isPending ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
