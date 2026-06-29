'use client'

import { Bell, ChevronRight, CircleHelp, Settings } from 'lucide-react'
import Image from 'next/image'
import Link from 'next/link'
import { useParams, usePathname } from 'next/navigation'
import { useOrganization } from '@clerk/nextjs'
import { useGetWorkspaceWorkspacesWorkspaceIdGet } from '@/api/generated/workspaces/workspaces'
import { useWorkspaceStream } from '@/hooks/useWorkspaceStream'

interface AppHeaderProps {
  orgId: string
}

function WorkspaceLiveStatus({ workspaceId }: { workspaceId: string }) {
  const { connected } = useWorkspaceStream(workspaceId)
  return (
    <div className="flex items-center gap-1.5">
      <span className={`h-2 w-2 rounded-full ${connected ? 'bg-success' : 'bg-muted'}`} />
      <span className="text-caption text-muted">{connected ? 'live' : 'offline'}</span>
    </div>
  )
}

function WorkspaceBreadcrumb({ workspaceId, orgId }: { workspaceId: string; orgId: string }) {
  const { data } = useGetWorkspaceWorkspacesWorkspaceIdGet(workspaceId)
  const name = data?.status === 200 ? data.data.name : workspaceId
  const pathname = usePathname()
  const base = `/orgs/${orgId}/workspaces/${workspaceId}`
  const segments = pathname.split('/').filter(Boolean)
  const section = segments.length > 4 ? segments[4] : null

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

  const orgName = organization?.name ?? '…'
  const workspacesHref = `/orgs/${orgId}/workspaces`

  return (
    <header className="flex h-14 shrink-0 items-center justify-between px-5">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1.5 min-w-0" aria-label="Breadcrumb">
        <Link href={workspacesHref} className="shrink-0 opacity-40 hover:opacity-90 transition-opacity">
          <Image src="/AppriseLogo.svg" alt="Apprise" width={16} height={16} className="brightness-0 invert" />
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
        {workspaceId && <WorkspaceLiveStatus workspaceId={workspaceId} />}
        <div className="flex items-center gap-0.5">
          <button
            aria-label="Help"
            className="rounded-md p-1.5 text-muted transition-colors hover:bg-elevated hover:text-foreground"
          >
            <CircleHelp size={16} />
          </button>
          <button
            aria-label="Settings"
            className="rounded-md p-1.5 text-muted transition-colors hover:bg-elevated hover:text-foreground"
          >
            <Settings size={16} />
          </button>
          <button
            aria-label="Notifications"
            className="rounded-md p-1.5 text-muted transition-colors hover:bg-elevated hover:text-foreground"
          >
            <Bell size={16} />
          </button>
        </div>
      </div>
    </header>
  )
}
