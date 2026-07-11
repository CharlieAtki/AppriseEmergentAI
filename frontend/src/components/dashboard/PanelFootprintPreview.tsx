import { GRID_COLS, GRID_ROWS } from '@/lib/dashboardGrid'

interface PanelFootprintPreviewProps {
  w: number
  h: number
}

// A miniature of the 12x7 canvas showing how much space this panel type
// actually occupies — real geometry, not a fabricated chart preview.
export function PanelFootprintPreview({ w, h }: PanelFootprintPreviewProps) {
  return (
    <div
      className="relative w-full overflow-hidden rounded-md border border-border bg-elevated"
      style={{ aspectRatio: `${GRID_COLS} / ${GRID_ROWS}` }}
    >
      <div
        className="absolute left-0 top-0 rounded-sm bg-brand-primary/20 ring-1 ring-inset ring-brand-primary/50"
        style={{ width: `${(w / GRID_COLS) * 100}%`, height: `${(h / GRID_ROWS) * 100}%` }}
      />
    </div>
  )
}
