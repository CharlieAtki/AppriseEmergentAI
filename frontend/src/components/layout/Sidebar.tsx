'use client'

import { useOrganization, UserButton } from '@clerk/nextjs'
import { WorkspaceSidebarSection } from './WorkspaceSidebarSection'

interface SidebarProps {
  orgId: string
}

export function Sidebar({ orgId }: SidebarProps) {
  const { organization } = useOrganization()

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex items-center gap-2.5 px-4 py-5">
        {organization?.imageUrl && (
          <img src={organization.imageUrl} alt="" className="h-6 w-6 rounded object-cover" />
        )}
        <span className="truncate text-sm font-medium text-foreground">
          {organization?.name}
        </span>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-2">
        <WorkspaceSidebarSection orgId={orgId} />
      </nav>

      <div className="border-t border-border px-4 py-4">
        <UserButton />
      </div>
    </aside>
  )
}
