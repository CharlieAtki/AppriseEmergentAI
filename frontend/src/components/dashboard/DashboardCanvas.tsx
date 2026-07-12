'use client'

import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
import { GridLayout } from 'react-grid-layout'
import type { Layout, ResizeHandleAxis } from 'react-grid-layout'
import { type PointerEvent as ReactPointerEvent, type Ref, useMemo } from 'react'
import { AnimatePresence, motion, useDragControls, useReducedMotion } from 'framer-motion'
import { DashboardPanel } from './DashboardPanel'
import { useContainerSize } from '@/hooks/useContainerSize'
import { pageSwipeSpring } from '@/lib/motion'
import { COMPACT_BREAKPOINT, COMPACT_ROW_HEIGHT, GRID_COLS, GRID_MARGIN, GRID_ROWS, toCompactLayout } from '@/lib/dashboardGrid'
import type { DashboardPanelInstance } from '@/lib/personalDashboard'

const RESIZE_HANDLES: ResizeHandleAxis[] = ['se']
const SWIPE_THRESHOLD = 80

function renderResizeHandle(axis: ResizeHandleAxis, ref: Ref<HTMLElement>) {
  return <span ref={ref as Ref<HTMLSpanElement>} className={`dashboard-resize-handle dashboard-resize-handle-${axis}`} />
}

const slideVariants = {
  enter: (direction: number) => ({ x: direction * 60, opacity: 0 }),
  center: { x: 0, opacity: 1 },
  exit: (direction: number) => ({ x: direction * -60, opacity: 0 }),
}

interface DashboardCanvasProps {
  workspaceId: string
  panels: DashboardPanelInstance[]
  page: number
  direction: number
  onLayoutChange: (layout: Layout) => void
  onSwipe: (direction: 1 | -1) => void
  onRemovePanel: (id: string) => void
  onMovePanel: (id: string, dx: number, dy: number) => void
  onUpdateConfig: (id: string, config: Record<string, unknown>) => void
}

// Owns canvas measurement, the grid itself — fixed 12x7 no-scroll above the
// compact breakpoint, a single scrollable column below it — and the
// swipe/slide transition between pages. Takes panels and callbacks only, no
// knowledge of the store. Uses the plain (non-responsive) GridLayout and
// derives the compact layout itself (see toCompactLayout) rather than RGL's
// own Responsive component, whose internal breakpoint-layout cache didn't
// reliably restore the desktop layout after shrinking past the breakpoint
// and back.
export function DashboardCanvas({
  workspaceId,
  panels,
  page,
  direction,
  onLayoutChange,
  onSwipe,
  onRemovePanel,
  onMovePanel,
  onUpdateConfig,
}: DashboardCanvasProps) {
  const { containerRef, width, height, mounted } = useContainerSize<HTMLDivElement>()
  const dragControls = useDragControls()
  const shouldReduceMotion = useReducedMotion()

  // Only render once we have a real measurement — a momentary 0 would
  // otherwise compute a 0px rowHeight and render every panel invisible.
  const canRenderGrid = mounted && width > 0 && height > 0
  const isCompact = canRenderGrid && width < COMPACT_BREAKPOINT
  const rowHeight = !canRenderGrid ? 0 : isCompact ? COMPACT_ROW_HEIGHT : (height - GRID_MARGIN[1] * (GRID_ROWS - 1)) / GRID_ROWS

  // Reference-stable when not compact (returns `panels` unchanged), so
  // React.memo on DashboardPanel still works on the desktop path.
  const displayPanels = useMemo(() => (isCompact ? toCompactLayout(panels) : panels), [isCompact, panels])

  function handlePointerDown(e: ReactPointerEvent<HTMLDivElement>) {
    if (shouldReduceMotion) return
    // Desktop panels handle their own drag via RGL, so swipe must only start
    // from empty canvas there. Compact mode disables panel dragging entirely
    // (position is meaningless in a forced single column), so there's no
    // conflict to guard against — swipe works from anywhere, including panels.
    if (!isCompact && (e.target as HTMLElement).closest('.react-grid-item')) return
    dragControls.start(e)
  }

  return (
    <div ref={containerRef} className="relative min-h-0 flex-1 overflow-hidden" onPointerDown={handlePointerDown}>
      {canRenderGrid && (
        <AnimatePresence initial={false} custom={direction}>
          <motion.div
            key={page}
            custom={direction}
            variants={slideVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={shouldReduceMotion ? { duration: 0 } : pageSwipeSpring}
            drag={shouldReduceMotion ? false : 'x'}
            dragControls={dragControls}
            dragListener={false}
            dragElastic={0.15}
            dragConstraints={{ left: 0, right: 0 }}
            dragMomentum={false}
            onDragEnd={(_, info) => {
              if (info.offset.x < -SWIPE_THRESHOLD) onSwipe(1)
              else if (info.offset.x > SWIPE_THRESHOLD) onSwipe(-1)
            }}
            className="absolute inset-0"
          >
            {/* Scrolls internally in compact mode; the outer canvas itself never scrolls. */}
            <div className={isCompact ? 'h-full overflow-y-auto overflow-x-hidden' : 'h-full overflow-hidden'}>
              <GridLayout
                width={width}
                layout={displayPanels}
                autoSize={isCompact}
                gridConfig={{
                  cols: isCompact ? 1 : GRID_COLS,
                  rowHeight,
                  margin: GRID_MARGIN,
                  containerPadding: [0, 0],
                  maxRows: isCompact ? Infinity : GRID_ROWS,
                }}
                dragConfig={{ handle: '.dashboard-panel-drag-handle', cancel: '.dashboard-panel-no-drag', enabled: !isCompact }}
                resizeConfig={{ handles: RESIZE_HANDLES, handleComponent: renderResizeHandle, enabled: !isCompact }}
                onLayoutChange={(layout) => {
                  // The compact single-column layout is derived, not
                  // authoritative — never persist it back into the store.
                  if (!isCompact) onLayoutChange(layout)
                }}
              >
                {displayPanels.map((panel, index) => (
                  <div key={panel.i}>
                    <DashboardPanel
                      workspaceId={workspaceId}
                      panel={panel}
                      index={index}
                      onRemove={onRemovePanel}
                      onMove={onMovePanel}
                      onUpdateConfig={onUpdateConfig}
                      moveDisabled={isCompact}
                    />
                  </div>
                ))}
              </GridLayout>
            </div>
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  )
}
