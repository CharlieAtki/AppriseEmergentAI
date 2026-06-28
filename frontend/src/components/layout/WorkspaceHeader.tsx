'use client'

import { ChevronLeft } from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

interface WorkspaceHeaderProps {
  connected: boolean
}

function deriveSection(pathname: string): string {
  const segments = pathname.split('/').filter(Boolean)
  // path shape: ['orgs', orgId, 'workspaces', workspaceId, ...section?]
  if (segments.length <= 4) return 'Overview'
  const section = segments[4] ?? ''
  return section.charAt(0).toUpperCase() + section.slice(1)
}

function deriveWorkspacesHref(pathname: string): string {
  const segments = pathname.split('/').filter(Boolean)
  // /orgs/[orgId]/workspaces
  return `/${segments.slice(0, 3).join('/')}`
}

export function WorkspaceHeader({ connected }: WorkspaceHeaderProps) {
  const pathname = usePathname()
  const section = deriveSection(pathname)
  const workspacesHref = deriveWorkspacesHref(pathname)

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-border px-6">
      <div>
        <Link
          href={workspacesHref}
          className="flex items-center gap-1 text-caption text-muted transition-colors hover:text-foreground"
        >
          <ChevronLeft size={12} />
          Workspaces
        </Link>
        <h1 className="text-title font-bold leading-tight text-foreground">{section}</h1>
      </div>

      <div className="flex items-center gap-2">
        {/*
         * Live indicator tied to WebSocket connection state.
         * Stays grey/offline until the backend stream endpoint
         * /workspaces/{id}/stream is built — see docs/frontend/frontend-gaps.md.
         */}
        <span className={`h-2 w-2 rounded-full ${connected ? 'bg-success' : 'bg-muted'}`} />
        <span className="text-caption text-muted">{connected ? 'live' : 'offline'}</span>
      </div>
    </header>
  )
}
