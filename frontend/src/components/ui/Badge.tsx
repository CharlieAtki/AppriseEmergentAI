import type { WorkspaceStatus } from '@/api/generated/model'

const statusStyles: Record<string, string> = {
  active:   'bg-success/10 text-success',
  inactive: 'bg-muted/10 text-muted',
  // Config provenance tiers — increasing color intensity as the value moves
  // further from the platform default, so an operator can tell at a glance
  // whether they're looking at an inherited value or an explicit override.
  platform:  'bg-muted/10 text-muted',
  org:       'bg-info/10 text-info',
  workspace: 'bg-brand-primary/10 text-brand-primary',
  // Task lifecycle (core.models.enums.TaskStatus) — reused for the live task
  // feed panel's per-row status pill.
  pending:   'bg-muted/10 text-muted',
  enriching: 'bg-muted/10 text-muted',
  open:      'bg-info/10 text-info',
  reserved:  'bg-warning/10 text-warning',
  executing: 'bg-info/10 text-info',
  completed: 'bg-success/10 text-success',
  failed:    'bg-error/10 text-error',
  expired:   'bg-muted/10 text-muted',
}

const fallback = 'bg-info/10 text-info'
interface BadgeProps {
  status: WorkspaceStatus | string
}

export function Badge({ status }: BadgeProps) {
  const styles = statusStyles[status] ?? fallback
  const label = status.charAt(0).toUpperCase() + status.slice(1)

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-label font-medium ${styles}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" />
      {label}
    </span>
  )
}
