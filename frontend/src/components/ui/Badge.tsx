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

  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${styles}`}>
      {status}
    </span>
  )
}
