'use client'

import { Button } from '@/components/ui/button'

import { useCallback } from 'react'
import type { Layout } from 'react-grid-layout'
import { DashboardCanvas } from './DashboardCanvas'
import { DashboardPagerArrow } from './DashboardPagerArrow'
import { DashboardPagerDots } from './DashboardPagerDots'
import { AddPanelDialog } from './AddPanelDialog'
import { usePersonalDashboard } from '@/hooks/dashboard/usePersonalDashboard'
import { useDashboardDevModeStore } from '@/stores/dashboardDevMode'
import { usePageDirection } from '@/hooks/dashboard/usePageDirection'
import { GRID_COLS } from '@/lib/dashboardGrid'
import { IconGridView, IconActivity } from '@/lib/icons'

interface DashboardGridProps {
  workspaceId: string
}

// Orchestrator only: reads the store, wires callbacks, and composes the
// canvas + pager + add-panel pieces. No grid math or animation logic lives
// here — see DashboardCanvas for the grid and swipe transition.
export function DashboardGrid({ workspaceId }: DashboardGridProps) {
  const { pages, activePage, setActivePage, setLayout, addPanel, removePanel, movePanel, updatePanelConfig } =
    usePersonalDashboard(workspaceId)
  const devModeEnabled = useDashboardDevModeStore((state) => state.enabled)
  const toggleDevMode = useDashboardDevModeStore((state) => state.toggle)

  const direction = usePageDirection(activePage)
  const isEmpty = pages.length === 1 && pages[0]!.length === 0
  const activePanels = pages[activePage] ?? []
  const pageCount = pages.length

  const goToPage = useCallback(
    (next: number) => {
      if (next < 0 || next >= pageCount) return
      setActivePage(next)
    },
    [pageCount, setActivePage],
  )

  // Stabilized per activePage so DashboardCanvas (and, through it, every
  // DashboardPanel) doesn't receive a new callback identity on every render —
  // only when the page actually changes. Panel drags/resizes update the
  // store without touching activePage, so these stay referentially stable
  // across that, letting React.memo on DashboardPanel actually take effect.
  const handleLayoutChange = useCallback((layout: Layout) => setLayout(activePage, layout), [activePage, setLayout])
  const handleSwipe = useCallback((swipeDirection: 1 | -1) => goToPage(activePage + swipeDirection), [activePage, goToPage])
  const handleMovePanel = useCallback(
    (id: string, dx: number, dy: number) => movePanel(activePage, id, dx, dy, GRID_COLS),
    [activePage, movePanel],
  )
  const handleUpdateConfig = useCallback(
    (id: string, config: Record<string, unknown>) => updatePanelConfig(activePage, id, config),
    [activePage, updatePanelConfig],
  )

  return (
    <div
      className="flex h-full flex-col"
      onKeyDown={(e) => {
        if (e.key === 'ArrowLeft') goToPage(activePage - 1)
        if (e.key === 'ArrowRight') goToPage(activePage + 1)
      }}
    >
      <header className="flex shrink-0 items-start justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="font-display text-heading text-foreground">Observability</h1>
          <p className="mt-0.5 text-body text-muted">Build your own view into what the agent pool is doing.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            onClick={toggleDevMode}
            aria-pressed={devModeEnabled}
            title="Preview panels with seeded mock data instead of real history"
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-body font-medium transition-colors ${
              devModeEnabled
                ? 'border-brand-primary bg-brand-primary/15 text-brand-primary'
                : 'border-border bg-elevated text-muted hover:text-foreground'
            }`}
          >
            <IconActivity size={14} />
            Dev data
          </Button>
          {!isEmpty && <AddPanelDialog onAddPanel={addPanel} />}
        </div>
      </header>

      <div className="dashboard-grid-canvas relative flex min-h-0 flex-1 flex-col gap-2 p-6">
        {isEmpty ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-border bg-surface">
              <IconGridView size={24} className="text-muted" />
            </div>
            <div>
              <p className="text-title font-semibold text-foreground">No panels yet</p>
              <p className="mt-1 text-body text-muted">Add your first panel to start building this view.</p>
            </div>
            <AddPanelDialog onAddPanel={addPanel} />
          </div>
        ) : (
          <>
            {pageCount > 1 && (
              <span className="sr-only" role="status" aria-live="polite">
                Page {activePage + 1} of {pageCount}
              </span>
            )}

            <DashboardCanvas
              workspaceId={workspaceId}
              panels={activePanels}
              page={activePage}
              direction={direction}
              onLayoutChange={handleLayoutChange}
              onSwipe={handleSwipe}
              onRemovePanel={removePanel}
              onMovePanel={handleMovePanel}
              onUpdateConfig={handleUpdateConfig}
            />
            <div className="flex h-11 shrink-0 items-center justify-center gap-1">
              {pageCount > 1 && (
                <>
                  <DashboardPagerArrow direction="prev" disabled={activePage === 0} onClick={() => goToPage(activePage - 1)} />
                  <DashboardPagerDots page={activePage} pageCount={pageCount} onChange={goToPage} />
                  <DashboardPagerArrow direction="next" disabled={activePage === pageCount - 1} onClick={() => goToPage(activePage + 1)} />
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
