'use client'

import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useCreateWorkspaceWorkspacesPost,
  getListWorkspacesWorkspacesGetQueryKey,
} from '@/api/generated/workspaces/workspaces'

interface CreateWorkspaceDialogProps {
  orgId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateWorkspaceDialog({ orgId, open, onOpenChange }: CreateWorkspaceDialogProps) {
  const [name, setName] = useState('')
  const queryClient = useQueryClient()
  const router = useRouter()

  const { mutate, isPending } = useCreateWorkspaceWorkspacesPost({
    mutation: {
      onSuccess: (response) => {
        if (response.status !== 201) return
        void queryClient.invalidateQueries({
          queryKey: getListWorkspacesWorkspacesGetQueryKey(),
        })
        onOpenChange(false)
        setName('')
        router.push(`/orgs/${orgId}/workspaces/${response.data.id}`)
      },
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    mutate({ data: { name: name.trim() } })
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-background/60 backdrop-blur-sm data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95">
          <Dialog.Title className="text-base font-semibold text-foreground">
            New workspace
          </Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted">
            Give your workspace a name to get started.
          </Dialog.Description>

          <form className="mt-5 space-y-4" onSubmit={handleSubmit}>
            <input
              autoFocus
              type="text"
              placeholder="e.g. Production"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-border bg-elevated px-3 py-2 text-sm text-foreground placeholder:text-muted focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
            />
            <div className="flex justify-end gap-2">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="rounded-lg px-4 py-2 text-sm text-muted transition-colors hover:text-foreground"
                >
                  Cancel
                </button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={!name.trim() || isPending}
                className="rounded-lg bg-brand-primary px-4 py-2 text-sm font-medium text-background transition-colors hover:bg-brand-hover disabled:opacity-50"
              >
                {isPending ? 'Creating…' : 'Create'}
              </button>
            </div>
          </form>

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
