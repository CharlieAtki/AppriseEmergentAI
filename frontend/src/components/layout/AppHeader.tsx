'use client'

import { Bell, ChevronRight, CircleHelp, Settings } from 'lucide-react'
import * as Tooltip from '@radix-ui/react-tooltip'
import { AppriseLogo } from '@/components/ui/AppriseLogo'

import Link from 'next/link'
import { useParams, useSelectedLayoutSegments } from 'next/navigation'
import { useState } from 'react'
import { useOrganization } from '@clerk/nextjs'
import { useGetWorkspaceWorkspacesWorkspaceIdGet } from '@/api/generated/workspaces/workspaces'
import { useWorkspaceStore } from '@/stores/workspace'
import { WorkspaceSettingsModal } from '@/components/workspaces/WorkspaceSettingsModal'

interface AppHeaderProps {
  orgId: string
}

function HeaderIconButton({
  label,
  onClick,
  children,
}: {
  label: string
  onClick?: () => void
  children: React.ReactNode
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <button
          aria-label={label}
          onClick={onClick}
          className="rounded-md p-1.5 text-muted transition-colors hover:bg-elevated hover:text-foreground"
        >
          {children}
        </button>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side="bottom"
          sideOffset={8}
          className="rounded bg-elevated px-2 py-1 text-caption text-muted shadow-md"
        >
          {label}
          <Tooltip.Arrow className="fill-elevated" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  )
}

function WorkspaceLiveStatus() {
  // useWorkspaceStream is mounted in workspaces/[workspaceId]/layout.tsx, a
  // sibling subtree of AppHeader (both under orgs/[orgId]/layout.tsx) — read
  // its connection status back out via the shared store instead of calling
  // the hook (and opening a second Centrifuge connection) here.
  const connected = useWorkspaceStore((s) => s.streamConnected)
  return (
    <div className="flex items-center gap-1.5">
      <span className={`h-2 w-2 rounded-full ${connected ? 'bg-success' : 'bg-muted'}`} />
      <span className="text-caption text-muted">{connected ? 'live' : 'offline'}</span>
    </div>
  )
}

function WorkspaceBreadcrumb({ workspaceId, orgId }: { workspaceId: string; orgId: string }) {
  const { data } = useGetWorkspaceWorkspacesWorkspaceIdGet(workspaceId)
  const name = data?.name ?? workspaceId
  const base = `/orgs/${orgId}/workspaces/${workspaceId}`
  // Relative to the nearest layout (orgs/[orgId]/layout.tsx): ['workspaces', workspaceId, section?]
  const segments = useSelectedLayoutSegments()
  const section = segments[2] ?? null

  return (
    <>
      <ChevronRight size={13} className="shrink-0 text-muted" />
      {section ? (
        <Link href={base} className="text-caption text-secondary hover:text-foreground transition-colors truncate max-w-[120px]">
          {name}
        </Link>
      ) : (
        <span className="text-caption text-foreground font-medium truncate max-w-[120px]">{name}</span>
      )}
      {section && (
        <>
          <ChevronRight size={13} className="shrink-0 text-muted" />
          <span className="text-caption text-foreground font-medium capitalize">{section}</span>
        </>
      )}
    </>
  )
}

export function AppHeader({ orgId }: AppHeaderProps) {
  const { organization } = useOrganization()
  const params = useParams<{ workspaceId?: string }>()
  const { workspaceId } = params
  const [settingsOpen, setSettingsOpen] = useState(false)

  const orgName = organization?.name ?? '…'
  const workspacesHref = `/orgs/${orgId}/workspaces`

  return (
    <Tooltip.Provider delayDuration={300}>
      <header className="flex h-14 shrink-0 items-center justify-between px-5">
        {/* Breadcrumbs */}
        <nav className="flex items-center gap-1.5 min-w-0" aria-label="Breadcrumb">
          <Link href={workspacesHref} className="shrink-0 opacity-40 hover:opacity-90 transition-opacity">
            <AppriseLogo className="h-4 w-auto brightness-0 invert" />
          </Link>
          <ChevronRight size={13} className="shrink-0 text-muted" />
          <span className="text-caption text-muted shrink-0 truncate max-w-[100px]">{orgName}</span>
          <ChevronRight size={13} className="shrink-0 text-muted" />
          {workspaceId ? (
            <Link href={workspacesHref} className="text-caption text-secondary hover:text-foreground transition-colors shrink-0">
              Workspaces
            </Link>
          ) : (
            <span className="text-caption text-foreground font-medium shrink-0">Workspaces</span>
          )}
          {workspaceId && (
            <WorkspaceBreadcrumb workspaceId={workspaceId} orgId={orgId} />
          )}
        </nav>

        {/* Right cluster */}
        <div className="flex items-center gap-3 shrink-0">
          {workspaceId && <WorkspaceLiveStatus />}
          <div className="flex items-center gap-0.5">
            <HeaderIconButton label="Help">
              <CircleHelp size={16} />
            </HeaderIconButton>
            {workspaceId && (
              <HeaderIconButton label="Workspace settings" onClick={() => setSettingsOpen(true)}>
                <Settings size={16} />
              </HeaderIconButton>
            )}
            <HeaderIconButton label="Notifications">
              <Bell size={16} />
            </HeaderIconButton>
          </div>
        </div>

        {workspaceId && (
          <WorkspaceSettingsModal workspaceId={workspaceId} open={settingsOpen} onOpenChange={setSettingsOpen} />
        )}
      </header>
    </Tooltip.Provider>
  )
}
