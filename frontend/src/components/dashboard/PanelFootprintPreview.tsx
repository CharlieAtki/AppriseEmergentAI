import type { Icon } from '@phosphor-icons/react'
import { GRID_COLS, GRID_ROWS } from '@/lib/dashboardGrid'

interface PanelFootprintPreviewProps {
  w: number
  h: number
  icon: Icon
  sizeLabel: string
}

// A miniature of the 12x7 canvas showing how much space this panel type
// actually occupies — real geometry, not a fabricated chart preview. The
// panel's own icon sits inside the highlighted footprint so the preview
// carries identity, not just size, at a glance. Sized via h-full from the
// parent rather than an aspect-ratio derived from width — an aspect-ratio
// here would recompute height off however wide the parent card happens to
// be, ignoring the parent's own fixed-height box and overflowing it. The
// inner highlight's proportions are percentages of this container, so
// footprint accuracy doesn't depend on the container matching 12:7 itself.
export function PanelFootprintPreview({ w, h, icon: PanelIcon, sizeLabel }: PanelFootprintPreviewProps) {
  return (
    <div className="relative h-full w-full overflow-hidden rounded-md border border-border bg-elevated">
      <div
        className="absolute left-0 top-0 flex items-center justify-center rounded-sm bg-brand-primary/20 ring-1 ring-inset ring-brand-primary/50"
        style={{ width: `${(w / GRID_COLS) * 100}%`, height: `${(h / GRID_ROWS) * 100}%` }}
      >
        <PanelIcon size={22} className="text-brand-primary" />
      </div>
      <span className="absolute bottom-1 right-1 rounded-full border border-border bg-background/80 px-1.5 py-0.5 text-caption font-semibold uppercase tracking-architectural text-muted">
        {sizeLabel}
      </span>
    </div>
  )
}
