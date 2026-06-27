'use client'

import { OrganizationSwitcher, UserButton } from '@clerk/nextjs'
import { WorkspaceSidebarSection } from './WorkspaceSidebarSection'

interface SidebarProps {
  orgId: string
}

export function Sidebar({ orgId }: SidebarProps) {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-surface">
      <div className="px-3 py-3 border-b border-border">
        <OrganizationSwitcher
          hidePersonal
          appearance={{
            elements: {
              rootBox: 'w-full',
              organizationSwitcherTrigger: 'w-full rounded-md px-1.5 py-1 text-sm text-foreground hover:bg-elevated transition-colors',
            },
          }}
        />
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-2">
        <WorkspaceSidebarSection orgId={orgId} />
      </nav>

      <div className="border-t border-border px-3 py-3">
        <UserButton />
      </div>
    </aside>
  )
}
