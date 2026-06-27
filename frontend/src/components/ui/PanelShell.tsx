interface PanelShellProps {
  title: string
  children?: React.ReactNode
  className?: string
}

export function PanelShell({ title, children, className }: PanelShellProps) {
  return (
    <div className={`flex flex-col overflow-hidden rounded-lg border border-border bg-surface ${className ?? ''}`}>
      <div className="border-b border-border px-4 py-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</span>
      </div>
      <div className="flex-1 p-4">{children}</div>
    </div>
  )
}
