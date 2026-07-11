import { memo, type KeyboardEvent } from 'react'
import { getPanelDefinition } from '@/lib/dashboardPanels'
import { IconClose, IconDragHandle } from '@/lib/icons'
import type { DashboardPanelInstance } from '@/stores/dashboardLayout'

interface DashboardPanelProps {
  panel: DashboardPanelInstance
  onRemove: (id: string) => void
  onMove: (id: string, dx: number, dy: number) => void
  /** True in compact/stacked mode, where x/y position is meaningless and RGL disables drag/resize. */
  moveDisabled?: boolean
}

const ARROW_MOVES: Record<string, [number, number]> = {
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
}

// Callbacks take the panel id rather than being pre-bound per instance, so
// the caller can pass the same stable function reference to every panel —
// required for React.memo below to actually skip re-rendering panels that
// weren't the one dragged/resized/moved.
export const DashboardPanel = memo(function DashboardPanel({ panel, onRemove, onMove, moveDisabled = false }: DashboardPanelProps) {
  const definition = getPanelDefinition(panel.panelType)
  const Icon = definition.icon

  // Keyboard-only path for repositioning, alongside pointer drag — required
  // per the design brief since the drag handle alone excludes keyboard users.
  // Disabled in compact mode along with drag/resize: nudging would silently
  // write into the canonical desktop layout's x/y from a view that doesn't
  // display position at all.
  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (moveDisabled) return
    if (e.target !== e.currentTarget) return
    const move = ARROW_MOVES[e.key]
    if (!move) return
    e.preventDefault()
    e.stopPropagation() // don't also trigger page-level pagination's arrow-key handler
    onMove(panel.i, ...move)
  }

  return (
    <div className="dashboard-panel group flex h-full flex-col overflow-hidden rounded-lg border border-border bg-surface">
      <div
        className={`dashboard-panel-drag-handle flex items-center justify-between gap-2 border-b border-border px-3 py-2 outline-none focus-visible:ring-1 focus-visible:ring-brand-primary ${
          moveDisabled ? '' : 'cursor-grab active:cursor-grabbing'
        }`}
        tabIndex={0}
        aria-label={moveDisabled ? `${definition.label} panel` : `${definition.label} panel. Drag or use arrow keys to move.`}
        onKeyDown={handleKeyDown}
      >
        <div className="flex min-w-0 items-center gap-2">
          <IconDragHandle size={12} className="shrink-0 text-muted" />
          <Icon size={13} className="shrink-0 text-muted" />
          <span className="truncate text-label font-semibold uppercase tracking-architectural text-muted">
            {definition.label}
          </span>
        </div>
        <button
          onClick={() => onRemove(panel.i)}
          aria-label={`Remove ${definition.label} panel`}
          className="dashboard-panel-no-drag shrink-0 rounded p-1 text-muted opacity-0 transition-opacity hover:bg-hover hover:text-foreground group-hover:opacity-100 focus-visible:opacity-100"
        >
          <IconClose size={12} />
        </button>
      </div>

      <div className="flex flex-1 items-center justify-center p-4">
        <span className="text-caption text-muted">
          {panel.w}×{panel.h} · Coming soon
        </span>
      </div>
    </div>
  )
})
