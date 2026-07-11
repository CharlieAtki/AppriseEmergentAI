import { IconChevronLeft, IconChevronRight } from '@/lib/icons'

interface DashboardPagerArrowProps {
  direction: 'prev' | 'next'
  disabled: boolean
  onClick: () => void
}

// Purely presentational — a single lightweight nav button, reused for both
// directions. No knowledge of the grid, the store, or the other navigation
// paths (dots, swipe, arrow keys). Sits inline in the pager row, not
// overlaid on the canvas. The button box is a full 44x44px touch target;
// only the icon inside reads as visually lightweight.
export function DashboardPagerArrow({ direction, disabled, onClick }: DashboardPagerArrowProps) {
  const Icon = direction === 'prev' ? IconChevronLeft : IconChevronRight

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={direction === 'prev' ? 'Previous page' : 'Next page'}
      className="flex h-11 w-11 items-center justify-center rounded text-muted outline-none transition-colors hover:text-foreground focus-visible:ring-1 focus-visible:ring-brand-primary disabled:pointer-events-none disabled:opacity-30"
    >
      <Icon size={14} />
    </button>
  )
}
