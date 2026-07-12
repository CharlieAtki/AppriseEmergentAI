'use client'

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from '@/components/ui/alert-dialog'
import { IconDelete } from '@/lib/icons'

interface ConfirmDeleteDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
  title: string
  description: React.ReactNode
}

// Shared shell for DeleteWorkspaceDialog / DeleteAgentDialog — both had an
// identical AlertDialog structure (icon medallion, title, description,
// cancel/delete footer) before this was extracted.
export function ConfirmDeleteDialog({ open, onOpenChange, onConfirm, title, description }: ConfirmDeleteDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="fixed left-1/2 top-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
        <div className="flex items-start gap-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-error/10">
            <IconDelete size={18} className="text-error" />
          </div>
          <div className="min-w-0">
            <AlertDialogTitle className="text-title font-semibold text-foreground">{title}</AlertDialogTitle>
            <AlertDialogDescription className="mt-1 text-body text-muted">{description}</AlertDialogDescription>
          </div>
        </div>

        <AlertDialogFooter className="mt-6 -mx-0 -mb-0 flex justify-end gap-2 rounded-none border-t-0 bg-transparent p-0">
          <AlertDialogCancel className="rounded-lg px-4 py-2 text-body text-muted transition-colors hover:text-foreground">
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            className="rounded-lg bg-error px-4 py-2 text-body font-medium text-white transition-colors hover:opacity-90"
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
