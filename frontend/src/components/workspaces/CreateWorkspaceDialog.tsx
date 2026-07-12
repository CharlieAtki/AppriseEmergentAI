'use client'

import { Button } from '@/components/ui/button'

import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Field, FieldLabel, FieldError } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { useEffect, useState } from 'react'
import { useWorkspaceCreate } from '@/hooks/workspace/useWorkspaceCreate'

interface CreateWorkspaceDialogProps {
  orgId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateWorkspaceDialog({ orgId: _orgId, open, onOpenChange }: CreateWorkspaceDialogProps) {
  const [name, setName] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const { createWorkspace, isPending } = useWorkspaceCreate()
  const nameMissing = submitted && name.trim().length === 0

  // Clear the draft whenever the dialog is dismissed so reopening starts fresh.
  useEffect(() => {
    if (!open) {
      setName('')
      setSubmitted(false)
    }
  }, [open])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="fixed left-1/2 top-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
        <DialogTitle className="text-title font-semibold text-foreground">
          New workspace
        </DialogTitle>
        <DialogDescription className="mt-1 text-body text-muted">
          Give your workspace a name to get started.
        </DialogDescription>

        <form
          className="mt-5 space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            setSubmitted(true)
            if (name.trim().length === 0) return
            createWorkspace(name.trim(), {
              onSuccess: () => {
                onOpenChange(false)
              },
            })
          }}
        >
          <Field data-invalid={nameMissing || undefined}>
            <FieldLabel htmlFor="new-workspace-name" className="text-label font-medium text-secondary">
              Name
            </FieldLabel>
            <Input
              id="new-workspace-name"
              autoFocus
              type="text"
              placeholder="e.g. Production"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={nameMissing}
              className="rounded-lg border-border bg-elevated px-3 py-2 text-body text-foreground placeholder:text-muted focus-visible:border-brand-primary focus-visible:ring-brand-primary"
            />
            {nameMissing && <FieldError>Name is required.</FieldError>}
          </Field>

          <div className="flex justify-end gap-2">
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
              {isPending ? 'Creating…' : 'Create'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
