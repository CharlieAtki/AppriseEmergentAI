export interface ChartTooltipRow {
  label: string;
  value: string;
  color?: string | undefined;
}

interface ChartTooltipCardProps {
  title?: string | undefined;
  rows: ChartTooltipRow[];
}

// The single visual source of truth for chart hover detail across the
// dashboard — wrapped by both ChartTooltip (recharts' content prop, for
// continuously cursor-tracked charts) and Agent Lanes' Radix Tooltip.Content
// (for discrete, individually-hoverable segments). Adds a border on top of
// the plain AppHeader/AppSidebar tooltip convention so a multi-row data card
// reads as a distinct surface, matching Dialog/Popover content elsewhere.
export function ChartTooltipCard({ title, rows }: ChartTooltipCardProps) {
  return (
    <div className="rounded border border-border bg-elevated px-2 py-1.5 text-caption shadow-md">
      {title && <p className="mb-1 text-muted">{title}</p>}
      <div className="flex flex-col gap-0.5">
        {rows.map((row, i) => (
          <div key={i} className="flex items-center gap-1.5">
            {row.color && (
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: row.color }}
              />
            )}
            <span className="text-muted">{row.label}</span>
            {row.value && (
              <span className="font-medium text-foreground">{row.value}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
