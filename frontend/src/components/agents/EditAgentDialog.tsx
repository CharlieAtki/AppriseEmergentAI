'use client'

import * as Dialog from '@radix-ui/react-dialog'
import * as Form from '@radix-ui/react-form'
import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useUpdateAgentWorkspacesWorkspaceIdAgentsAgentIdPatch,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
} from '@/api/generated/agents/agents'
import { IconAgent, IconClose } from '@/lib/icons'
import type { AgentResponse } from '@/api/generated/fastAPI.schemas'

interface EditAgentDialogProps {
  agent: AgentResponse
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function EditAgentDialog({ agent, open, onOpenChange }: EditAgentDialogProps) {
  const [name, setName] = useState(agent.name)
  const queryClient = useQueryClient()

  useEffect(() => {
    if (open) setName(agent.name)
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
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay fixed inset-0 z-50 bg-background/60 backdrop-blur-sm" />
        <Dialog.Content className="dialog-content fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-primary/15 text-brand-primary">
              <IconAgent size={18} />
            </div>
            <div>
              <Dialog.Title className="text-title font-semibold text-foreground">
                Edit agent
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 text-body text-muted">
                Update the agent's name.
              </Dialog.Description>
            </div>
          </div>

          <Form.Root
            className="mt-5 space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              mutate({ workspaceId: agent.workspace_id, agentId: agent.id, data: { name: name.trim() } })
            }}
          >
            <Form.Field name="name" className="space-y-1.5">
              <Form.Label className="text-label font-medium text-secondary">Name</Form.Label>
              <Form.Control asChild>
                <input
                  autoFocus
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-lg border border-border bg-elevated px-3 py-2 text-body text-foreground placeholder:text-muted focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
                />
              </Form.Control>
              <Form.Message match="valueMissing" className="text-caption text-error">
                Name is required.
              </Form.Message>
            </Form.Field>

            <div className="flex justify-end gap-2 pt-1">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="rounded-lg px-4 py-2 text-body text-muted transition-colors hover:text-foreground"
                >
                  Cancel
                </button>
              </Dialog.Close>
              <Form.Submit asChild>
                <button
                  disabled={isPending}
                  className="rounded-lg bg-brand-primary px-4 py-2 text-body font-medium text-background transition-colors hover:bg-brand-hover disabled:opacity-50"
                >
                  {isPending ? 'Saving…' : 'Save'}
                </button>
              </Form.Submit>
            </div>
          </Form.Root>

          <Dialog.Close asChild>
            <button
              className="absolute right-4 top-4 text-muted transition-colors hover:text-foreground"
              aria-label="Close"
            >
              <IconClose size={16} />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
