'use client'

import { Button } from '@/components/ui/button'

import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Field, FieldLabel, FieldError } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useUpdateWorkspaceWorkspacesWorkspaceIdPatch,
  getListWorkspacesWorkspacesGetQueryKey,
  getGetWorkspaceWorkspacesWorkspaceIdGetQueryKey,
} from '@/api/generated/workspaces/workspaces'
import { WorkspaceStatus } from '@/api/generated/model'
import type { WorkspaceResponse } from '@/api/generated/model'
import { toast } from 'sonner'

interface EditWorkspaceDialogProps {
  workspace: WorkspaceResponse
  open: boolean
  onOpenChange: (open: boolean) => void
}

const STATUS_ITEMS = WorkspaceStatus.options.map((s) => ({
  label: s.charAt(0).toUpperCase() + s.slice(1),
  value: s,
}))

export function EditWorkspaceDialog({ workspace, open, onOpenChange }: EditWorkspaceDialogProps) {
  const [name, setName] = useState(workspace.name)
  const [status, setStatus] = useState<WorkspaceStatus>(workspace.status)
  const [submitted, setSubmitted] = useState(false)
  const queryClient = useQueryClient()
  const nameMissing = submitted && name.trim().length === 0

  // Sync local state from the (potentially cache-refreshed) workspace prop each time the dialog opens.
  useEffect(() => {
    if (open) {
      setName(workspace.name)
      setStatus(workspace.status)
    }
  }, [open, workspace.name, workspace.status])

  const { mutate, isPending } = useUpdateWorkspaceWorkspacesWorkspaceIdPatch({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getListWorkspacesWorkspacesGetQueryKey() })
        void queryClient.invalidateQueries({
          queryKey: getGetWorkspaceWorkspacesWorkspaceIdGetQueryKey(workspace.id),
        })
        onOpenChange(false)
      },
      onError: () => {
        toast.error('Failed to update workspace', { description: workspace.name })
      },
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="fixed left-1/2 top-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
        <DialogTitle className="text-title font-semibold text-foreground">
          Edit workspace
        </DialogTitle>
        <DialogDescription className="mt-1 text-body text-muted">
          Update the workspace name or status.
        </DialogDescription>

        <form
          className="mt-5 space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            setSubmitted(true)
            if (name.trim().length === 0) return
            mutate({ workspaceId: workspace.id, data: { name: name.trim(), status } })
          }}
        >
          <Field data-invalid={nameMissing || undefined}>
            <FieldLabel htmlFor="edit-workspace-name" className="text-label font-medium text-secondary">
              Name
            </FieldLabel>
            <Input
              id="edit-workspace-name"
              autoFocus
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={nameMissing}
              className="rounded-lg border-border bg-elevated px-3 py-2 text-body text-foreground placeholder:text-muted focus-visible:border-brand-primary focus-visible:ring-brand-primary"
            />
            {nameMissing && <FieldError>Name is required.</FieldError>}
          </Field>

          <Field>
            <FieldLabel htmlFor="edit-workspace-status" className="text-label font-medium text-secondary">
              Status
            </FieldLabel>
            <Select items={STATUS_ITEMS} value={status} onValueChange={(v) => setStatus(v as WorkspaceStatus)}>
              <SelectTrigger
                id="edit-workspace-status"
                className="w-full justify-between rounded-lg border-border bg-elevated px-3 py-2 text-body text-foreground hover:border-brand-primary focus-visible:border-brand-primary focus-visible:ring-brand-primary"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="w-(--anchor-width) rounded-lg border-border bg-elevated shadow-xl">
                {STATUS_ITEMS.map((item) => (
                  <SelectItem key={item.value} value={item.value} className="text-body">
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
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
