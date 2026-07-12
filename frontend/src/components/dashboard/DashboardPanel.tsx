import { Button } from '@/components/ui/button'
import { memo, type KeyboardEvent, useState } from 'react'
import { Popover, PopoverTrigger, PopoverContent, PopoverArrow } from '@/components/ui/popover'
import { getPanelDefinition } from '@/lib/dashboardPanels'
import { IconClose, IconDragHandle, IconSettings } from '@/lib/icons'
import type { DashboardPanelInstance } from '@/stores/dashboardLayout'
import { PanelEmptyState } from './panels/PanelEmptyState'

interface DashboardPanelProps {
  workspaceId: string
  panel: DashboardPanelInstance
  onRemove: (id: string) => void
  onMove: (id: string, dx: number, dy: number) => void
  onUpdateConfig: (id: string, config: Record<string, unknown>) => void
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
export const DashboardPanel = memo(function DashboardPanel({
  workspaceId,
  panel,
  onRemove,
  onMove,
  onUpdateConfig,
  moveDisabled = false,
}: DashboardPanelProps) {
  const definition = getPanelDefinition(panel.panelType)
  const Icon = definition.icon
  const [settingsOpen, setSettingsOpen] = useState(false)
  const Body = definition.Body
  const ConfigForm = definition.ConfigForm

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
        <div className="dashboard-panel-no-drag flex shrink-0 items-center gap-0.5">
          {ConfigForm && (
            <Popover open={settingsOpen} onOpenChange={setSettingsOpen}>
              <PopoverTrigger
                render={
                  <Button
                    aria-label={`${definition.label} panel settings`}
                    variant="ghost"
                    size="icon"
                    className="rounded p-1 text-muted opacity-0 transition-opacity hover:bg-hover hover:text-foreground group-hover:opacity-100 focus-visible:opacity-100"
                  />
                }
              >
                <IconSettings size={12} />
              </PopoverTrigger>
              <PopoverContent
                side="bottom"
                align="end"
                sideOffset={6}
                className="popover-content z-50 w-64 rounded-xl border border-border bg-elevated p-4 shadow-xl"
              >
                <p className="mb-3 text-label font-semibold uppercase tracking-architectural text-muted">
                  {definition.label} settings
                </p>
                <ConfigForm
                  workspaceId={workspaceId}
                  config={panel.config}
                  onChange={(config) => onUpdateConfig(panel.i, config)}
                />
                <PopoverArrow />
              </PopoverContent>
            </Popover>
          )}
          <Button
            onClick={() => onRemove(panel.i)}
            aria-label={`Remove ${definition.label} panel`}
            variant="ghost"
            size="icon"
            className="rounded p-1 text-muted opacity-0 transition-opacity hover:bg-hover hover:text-foreground group-hover:opacity-100 focus-visible:opacity-100"
          >
            <IconClose size={12} />
          </Button>
        </div>
      </div>

      <div className="flex flex-1 flex-col overflow-hidden">
        {Body ? <Body workspaceId={workspaceId} panel={panel} /> : <PanelEmptyState message="Coming soon." />}
      </div>
    </div>
  )
})
