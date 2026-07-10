'use client'

import * as Tooltip from '@radix-ui/react-tooltip'
import { OrganizationSwitcher, useClerk, useOrganization, useUser } from '@clerk/nextjs'
import {
  Activity,
  BarChart2,
  BookOpen,
  CheckSquare,
  LayoutDashboard,
  LogOut,
  ScrollText,
  Settings,
} from 'lucide-react'
import Link from 'next/link'
import { useParams, usePathname } from 'next/navigation'
import { useState } from 'react'
import { OrgSettingsModal } from '@/components/organisations/OrgSettingsModal'
import { WorkspaceSidebarSection } from './WorkspaceSidebarSection'

interface NavItem {
  label: string
  Icon: React.ElementType
  segment: string | null
  disabled?: boolean
}

const PLATFORM_NAV: NavItem[] = [
  { label: 'Overview', Icon: LayoutDashboard, segment: null },
  { label: 'Agents',   Icon: Activity,        segment: 'agents' },
  { label: 'Tasks',    Icon: CheckSquare,     segment: 'tasks' },
  { label: 'Skills',   Icon: BookOpen,        segment: 'skills',   disabled: true },
  { label: 'Runs',     Icon: BarChart2,       segment: 'runs',     disabled: true },
  { label: 'Logs',     Icon: ScrollText,      segment: 'logs',     disabled: true },
]

function UserStrip() {
  const { user } = useUser()
  const { membership } = useOrganization()
  const { signOut } = useClerk()

  const displayName =
    user?.username ?? user?.firstName ?? user?.primaryEmailAddress?.emailAddress ?? '…'
  const initial = displayName.charAt(0).toUpperCase()
  const rawRole = (membership as { role?: string } | null)?.role ?? ''
  const role = rawRole.replace(/^org:/, '')
  const roleLabel = role ? role.charAt(0).toUpperCase() + role.slice(1) : 'Member'

  return (
    <div className="flex items-center gap-2.5 px-1">
      <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-primary/20 text-caption font-semibold text-brand-primary">
        {initial}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-body font-medium leading-tight text-foreground">{displayName}</p>
        <p className="text-caption leading-tight text-muted">{roleLabel}</p>
      </div>
      <button
        onClick={() => void signOut()}
        aria-label="Sign out"
        className="shrink-0 rounded-md p-1 text-muted transition-colors hover:bg-error/10 hover:text-error"
      >
        <LogOut size={14} />
      </button>
    </div>
  )
}

interface AppSidebarProps {
  orgId: string
}

export function AppSidebar({ orgId }: AppSidebarProps) {
  const pathname = usePathname()
  const params = useParams<{ workspaceId?: string }>()
  const { workspaceId } = params
  const [orgSettingsOpen, setOrgSettingsOpen] = useState(false)

  const base = workspaceId ? `/orgs/${orgId}/workspaces/${workspaceId}` : null

  function isActive(segment: string | null): boolean {
    if (!base) return false
    if (segment === null) return pathname === base
    return pathname.startsWith(`${base}/${segment}`)
  }

  return (
    <Tooltip.Provider delayDuration={300}>
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-sidebar">
        {/* Org switcher — no bottom border, tighter appearance */}
        <div className="flex items-center gap-1.5 px-3 py-3">
          <div className="min-w-0 flex-1">
            <OrganizationSwitcher
              hidePersonal
              appearance={{
                elements: {
                  rootBox: 'w-full',
                  organizationSwitcherTrigger:
                    'w-full flex items-center gap-2 rounded-lg px-2 py-2 text-body font-medium text-foreground bg-white/10 transition-colors',
                  organizationPreviewMainIdentifier: 'text-body font-medium text-foreground',
                  organizationPreviewSecondaryIdentifier: 'hidden',
                  organizationSwitcherTriggerIcon: 'text-muted ml-auto',
                },
              }}
            />
          </div>
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
              <button
                onClick={() => setOrgSettingsOpen(true)}
                aria-label="Organisation settings"
                className="shrink-0 rounded-md p-2 text-muted transition-colors hover:bg-elevated hover:text-foreground"
              >
                <Settings size={16} />
              </button>
            </Tooltip.Trigger>
            <Tooltip.Portal>
              <Tooltip.Content
                side="bottom"
                sideOffset={8}
                className="rounded bg-elevated px-2 py-1 text-caption text-muted shadow-md"
              >
                Organisation settings
                <Tooltip.Arrow className="fill-elevated" />
              </Tooltip.Content>
            </Tooltip.Portal>
          </Tooltip.Root>
        </div>

        <OrgSettingsModal orgId={orgId} open={orgSettingsOpen} onOpenChange={setOrgSettingsOpen} />

        <nav className="flex-1 overflow-y-auto px-2 py-2 space-y-4">
          {/* Workspaces */}
          <WorkspaceSidebarSection orgId={orgId} />

          {/* Platform */}
          <div>
            <p className="mb-1 px-2 text-label font-semibold uppercase tracking-architectural text-muted">
              Platform
            </p>
            <ul className="space-y-0.5">
              {PLATFORM_NAV.map(({ label, Icon, segment, disabled }) => {
                const active = !disabled && isActive(segment)
                const href = base
                  ? segment === null
                    ? base
                    : `${base}/${segment}`
                  : null

                const cls = [
                  'flex w-full items-center gap-3 py-2 text-body transition-colors',
                  active
                    ? 'rounded-r-md border-l-2 border-brand-primary bg-brand-primary/10 pl-[10px] pr-3 font-medium text-brand-primary'
                    : disabled || !href
                      ? 'cursor-not-allowed rounded-md px-3 opacity-50 text-muted'
                      : 'rounded-md px-3 text-secondary hover:bg-elevated hover:text-foreground',
                ].join(' ')

                const inner = (
                  <>
                    <Icon size={16} className="shrink-0" />
                    {label}
                  </>
                )

                if (!href || disabled) {
                  return (
                    <li key={label}>
                      <Tooltip.Root>
                        <Tooltip.Trigger asChild>
                          <span className={cls}>{inner}</span>
                        </Tooltip.Trigger>
                        <Tooltip.Portal>
                          <Tooltip.Content
                            side="right"
                            sideOffset={8}
                            className="rounded bg-elevated px-2 py-1 text-caption text-muted shadow-md"
                          >
                            {disabled ? 'Coming soon' : 'Select a workspace'}
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
                      {inner}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        </nav>

        {/* User strip */}
        <div className="border-t border-border px-3 py-3">
          <UserStrip />
        </div>
      </aside>
    </Tooltip.Provider>
  )
}
