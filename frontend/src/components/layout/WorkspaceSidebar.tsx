'use client'

import * as Tooltip from '@radix-ui/react-tooltip'
import {
  Activity,
  BarChart2,
  BookOpen,
  CheckSquare,
  LayoutDashboard,
  ScrollText,
  Settings,
} from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

interface NavItem {
  label: string
  Icon: React.ElementType
  segment: string | null
  disabled?: boolean
}

const NAV: NavItem[] = [
  { label: 'Overview', Icon: LayoutDashboard, segment: null },
  { label: 'Agents',   Icon: Activity,        segment: 'agents' },
  { label: 'Tasks',    Icon: CheckSquare,     segment: 'tasks' },
  { label: 'Skills',   Icon: BookOpen,        segment: 'skills',   disabled: true },
  { label: 'Runs',     Icon: BarChart2,       segment: 'runs',     disabled: true },
  { label: 'Logs',     Icon: ScrollText,      segment: 'logs',     disabled: true },
  { label: 'Settings', Icon: Settings,        segment: 'settings', disabled: true },
]

interface WorkspaceSidebarProps {
  orgId: string
  workspaceId: string
  workspaceName: string
}

export function WorkspaceSidebar({ orgId, workspaceId, workspaceName }: WorkspaceSidebarProps) {
  const pathname = usePathname()
  const base = `/orgs/${orgId}/workspaces/${workspaceId}`

  function isActive(segment: string | null): boolean {
    if (segment === null) return pathname === base
    return pathname.startsWith(`${base}/${segment}`)
  }

  return (
    <Tooltip.Provider delayDuration={300}>
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-sidebar">
        <div className="flex h-16 shrink-0 flex-col justify-center border-b border-border px-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Workspace</p>
          <p className="mt-0.5 truncate text-sm font-medium text-foreground">{workspaceName}</p>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 py-3">
          <ul className="space-y-0.5">
            {NAV.map(({ label, Icon, segment, disabled }) => {
              const active = !disabled && isActive(segment)
              const href = segment === null ? base : `${base}/${segment}`

              const cls = [
                'flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                active
                  ? 'bg-brand-primary/10 font-medium text-brand-primary'
                  : disabled
                    ? 'cursor-not-allowed opacity-50 text-muted'
                    : 'text-secondary hover:bg-elevated hover:text-foreground',
              ].join(' ')

              if (disabled) {
                return (
                  <li key={label}>
                    <Tooltip.Root>
                      <Tooltip.Trigger asChild>
                        <span className={cls}>
                          <Icon size={16} className="shrink-0" />
                          {label}
                        </span>
                      </Tooltip.Trigger>
                      <Tooltip.Portal>
                        <Tooltip.Content
                          side="right"
                          sideOffset={8}
                          className="rounded bg-elevated px-2 py-1 text-xs text-muted shadow-md"
                        >
                          Coming soon
                          <Tooltip.Arrow className="fill-elevated" />
                        </Tooltip.Content>
                      </Tooltip.Portal>
                    </Tooltip.Root>
                  </li>
                )
              }

              return (
                <li key={label}>
                  <Link href={href} className={cls}>
                    <Icon size={16} className="shrink-0" />
                    {label}
                  </Link>
                </li>
              )
            })}
          </ul>
        </nav>
      </aside>
    </Tooltip.Provider>
  )
}
