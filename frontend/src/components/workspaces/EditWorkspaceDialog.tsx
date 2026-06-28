'use client'

import * as Dialog from '@radix-ui/react-dialog'
import * as Form from '@radix-ui/react-form'
import * as Select from '@radix-ui/react-select'
import { ChevronDown, Check, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useUpdateWorkspaceWorkspacesWorkspaceIdPatch,
  getListWorkspacesWorkspacesGetQueryKey,
} from '@/api/generated/workspaces/workspaces'
import { UpdateWorkspaceRequestStatus, type WorkspaceResponse } from '@/api/generated/fastAPI.schemas'

interface EditWorkspaceDialogProps {
  workspace: WorkspaceResponse
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function EditWorkspaceDialog({ workspace, open, onOpenChange }: EditWorkspaceDialogProps) {
  const [name, setName] = useState(workspace.name)
  const [status, setStatus] = useState<typeof UpdateWorkspaceRequestStatus[keyof typeof UpdateWorkspaceRequestStatus]>(
    workspace.status in UpdateWorkspaceRequestStatus
      ? workspace.status as typeof UpdateWorkspaceRequestStatus[keyof typeof UpdateWorkspaceRequestStatus]
      : UpdateWorkspaceRequestStatus.active
  )
  const queryClient = useQueryClient()

  // Sync local state from the (potentially cache-refreshed) workspace prop each time the dialog opens.
  useEffect(() => {
    if (open) {
      setName(workspace.name)
      setStatus(
        workspace.status in UpdateWorkspaceRequestStatus
          ? workspace.status as typeof UpdateWorkspaceRequestStatus[keyof typeof UpdateWorkspaceRequestStatus]
          : UpdateWorkspaceRequestStatus.active
      )
    }
  }, [open, workspace.name, workspace.status])

  const { mutate, isPending } = useUpdateWorkspaceWorkspacesWorkspaceIdPatch({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getListWorkspacesWorkspacesGetQueryKey() })
        onOpenChange(false)
      },
    },
  })

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay fixed inset-0 bg-background/60 backdrop-blur-sm" />
        <Dialog.Content className="dialog-content fixed left-1/2 top-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
          <Dialog.Title className="text-base font-semibold text-foreground">
            Edit workspace
          </Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted">
            Update the workspace name or status.
          </Dialog.Description>

          <Form.Root
            className="mt-5 space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              mutate({ workspaceId: workspace.id, data: { name: name.trim(), status } })
            }}
          >
            <Form.Field name="name" className="space-y-1.5">
              <Form.Label className="text-xs font-medium text-secondary">Name</Form.Label>
              <Form.Control asChild>
                <input
                  autoFocus
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-lg border border-border bg-elevated px-3 py-2 text-sm text-foreground placeholder:text-muted focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
                />
              </Form.Control>
              <Form.Message match="valueMissing" className="text-xs text-error">
                Name is required.
              </Form.Message>
            </Form.Field>

            <Form.Field name="status" className="space-y-1.5">
              <Form.Label className="text-xs font-medium text-secondary">Status</Form.Label>
              {/* Hidden input so Radix Form sees the value — Select.Root manages visual state */}
              <input type="hidden" name="status" value={status ?? UpdateWorkspaceRequestStatus.active} />
              <Select.Root
                value={status ?? UpdateWorkspaceRequestStatus.active}
                onValueChange={(v) => setStatus(v as typeof UpdateWorkspaceRequestStatus[keyof typeof UpdateWorkspaceRequestStatus])}
              >
                <Select.Trigger className="flex w-full items-center justify-between rounded-lg border border-border bg-elevated px-3 py-2 text-sm text-foreground transition-colors hover:border-brand-primary focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary data-[placeholder]:text-muted">
                  <Select.Value />
                  <Select.Icon>
                    <ChevronDown size={14} className="text-muted" />
                  </Select.Icon>
                </Select.Trigger>

                <Select.Portal>
                  <Select.Content
                    position="popper"
                    sideOffset={4}
                    className="z-50 w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border border-border bg-elevated shadow-xl"
                  >
                    <Select.Viewport className="p-1">
                      {Object.values(UpdateWorkspaceRequestStatus).map((s) => (
                        <Select.Item
                          key={s}
                          value={s}
                          className="flex cursor-pointer items-center justify-between rounded-md px-3 py-1.5 text-sm text-foreground outline-none transition-colors hover:bg-hover data-[highlighted]:bg-hover data-[state=checked]:text-brand-primary"
                        >
                          <Select.ItemText>{s.charAt(0).toUpperCase() + s.slice(1)}</Select.ItemText>
                          <Select.ItemIndicator>
                            <Check size={13} className="text-brand-primary" />
                          </Select.ItemIndicator>
                        </Select.Item>
                      ))}
                    </Select.Viewport>
                  </Select.Content>
                </Select.Portal>
              </Select.Root>
            </Form.Field>

            <div className="flex justify-end gap-2 pt-1">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="rounded-lg px-4 py-2 text-sm text-muted transition-colors hover:text-foreground"
                >
                  Cancel
                </button>
              </Dialog.Close>
              <Form.Submit asChild>
                <button
                  disabled={isPending}
                  className="rounded-lg bg-brand-primary px-4 py-2 text-sm font-medium text-background transition-colors hover:bg-brand-hover disabled:opacity-50"
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
              <X size={16} />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
