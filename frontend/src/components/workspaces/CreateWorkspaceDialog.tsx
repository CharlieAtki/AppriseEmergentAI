'use client'

import * as Dialog from '@radix-ui/react-dialog'
import * as Form from '@radix-ui/react-form'
import { X } from 'lucide-react'
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useCreateWorkspaceWorkspacesPost,
  getListWorkspacesWorkspacesGetQueryKey,
} from '@/api/generated/workspaces/workspaces'
import { useToastStore } from '@/stores/toast'

interface CreateWorkspaceDialogProps {
  orgId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateWorkspaceDialog({ orgId: _orgId, open, onOpenChange }: CreateWorkspaceDialogProps) {
  const [name, setName] = useState('')
  const queryClient = useQueryClient()
  const { toast } = useToastStore()

  const { mutate, isPending } = useCreateWorkspaceWorkspacesPost({
    mutation: {
      onSuccess: (response) => {
        // Narrows the discriminated union — Axios throws on 422 so this branch is always taken.
        if (response.status !== 201) return
        void queryClient.invalidateQueries({ queryKey: getListWorkspacesWorkspacesGetQueryKey() })
        onOpenChange(false)
        toast({ title: 'Workspace created', description: response.data.name, variant: 'success' })
        setName('')
      },
    },
  })

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay fixed inset-0 bg-background/60 backdrop-blur-sm" />
        <Dialog.Content className="dialog-content fixed left-1/2 top-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
          <Dialog.Title className="text-title font-semibold text-foreground">
            New workspace
          </Dialog.Title>
          <Dialog.Description className="mt-1 text-body text-muted">
            Give your workspace a name to get started.
          </Dialog.Description>

          <Form.Root
            className="mt-5 space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              mutate({ data: { name: name.trim() } })
            }}
          >
            <Form.Field name="name" className="space-y-1.5">
              <Form.Label className="text-label font-medium text-secondary">Name</Form.Label>
              <Form.Control asChild>
                <input
                  autoFocus
                  type="text"
                  required
                  placeholder="e.g. Production"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-lg border border-border bg-elevated px-3 py-2 text-body text-foreground placeholder:text-muted focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
                />
              </Form.Control>
              <Form.Message match="valueMissing" className="text-caption text-error">
                Name is required.
              </Form.Message>
            </Form.Field>

            <div className="flex justify-end gap-2">
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
                  {isPending ? 'Creating…' : 'Create'}
                </button>
              </Form.Submit>
            </div>
          </Form.Root>

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
