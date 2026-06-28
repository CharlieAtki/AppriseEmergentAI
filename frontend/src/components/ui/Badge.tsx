const statusStyles: Record<string, string> = {
  active:   'bg-success/10 text-success',
  inactive: 'bg-muted/10 text-muted',
}

const fallback = 'bg-info/10 text-info'

interface BadgeProps {
  status: string
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
