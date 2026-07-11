import { IconAnalytics } from '@/lib/icons'

interface PanelEmptyStateProps {
  message: string
}

// Shared "not enough activity yet" treatment — used identically by Agent Pool
// sparklines (<2 influence snapshots) and Agent Lanes (no executions in the
// selected window). Static, no motion: there's nothing happening to animate.
export function PanelEmptyState({ message }: PanelEmptyStateProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-1.5 p-2 text-center">
      <IconAnalytics size={16} className="text-muted" />
      <p className="text-caption text-muted">{message}</p>
    </div>
  )
}
