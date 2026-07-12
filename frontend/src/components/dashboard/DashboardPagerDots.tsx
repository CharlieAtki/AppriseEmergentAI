import { Button } from '@/components/ui/button'
interface DashboardPagerDotsProps {
  page: number
  pageCount: number
  onChange: (page: number) => void
}

// Purely presentational — same contract as DashboardPagerArrow. Renders just
// the dots themselves; the parent owns the row that combines them with the
// prev/next arrows. Each button is a 44x44px touch target with a small
// visual dot centered inside — the hit area, not the dot, grows.
export function DashboardPagerDots({ page, pageCount, onChange }: DashboardPagerDotsProps) {
  if (pageCount <= 1) return null

  return (
    <>
      {Array.from({ length: pageCount }, (_, i) => (
        <Button
          key={i}
          onClick={() => onChange(i)}
          aria-label={`Go to page ${i + 1}`}
          aria-current={i === page}
          variant="icon"
          className="group flex h-11 w-11 items-center justify-center rounded outline-none focus-visible:ring-1 focus-visible:ring-brand-primary"
        >
          <span
            className={`h-1.5 rounded-full transition-all ${
              i === page ? 'w-4 bg-brand-primary' : 'w-1.5 bg-hover group-hover:bg-border'
            }`}
          />
        </Button>
      ))}
    </>
  )
}
