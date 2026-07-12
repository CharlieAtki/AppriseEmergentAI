'use client'

import { IconHelp, IconNotifications, IconSettings } from '@/lib/icons'
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from '@/components/ui/breadcrumb'
import { Button } from '@/components/ui/button'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { AppriseLogo } from '@/components/ui/AppriseLogo'
import Link from 'next/link'
import { useParams, useSelectedLayoutSegments } from 'next/navigation'
import { useState } from 'react'
import { useOrganization } from '@clerk/nextjs'
import { useGetWorkspaceWorkspacesWorkspaceIdGet } from '@/api/generated/workspaces/workspaces'
import { useWorkspaceStore } from '@/stores/workspace'
import { WorkspaceSettingsModal } from '@/components/workspaces/WorkspaceSettingsModal'

interface AppHeaderProps { orgId: string }

function HeaderIconButton({ label, onClick, children }: { label: string; onClick?: () => void; children: React.ReactNode }) {
  return <Tooltip><TooltipTrigger render={<Button type="button" variant="ghost" size="icon-sm" aria-label={label} onClick={onClick} />}>{children}</TooltipTrigger><TooltipContent side="bottom" sideOffset={8}>{label}</TooltipContent></Tooltip>
}

function WorkspaceLiveStatus() {
  const connected = useWorkspaceStore((s) => s.streamConnected)
  return <div className="flex items-center gap-1.5"><span className={`size-2 rounded-full ${connected ? 'bg-success' : 'bg-muted'}`} /><span className="text-caption text-muted">{connected ? 'live' : 'offline'}</span></div>
}

function WorkspaceBreadcrumbItems({ workspaceId, orgId }: { workspaceId: string; orgId: string }) {
  const { data } = useGetWorkspaceWorkspacesWorkspaceIdGet(workspaceId)
  const name = data?.name ?? workspaceId
  const base = `/orgs/${orgId}/workspaces/${workspaceId}`
  const section = useSelectedLayoutSegments()[2] ?? null
  return <>
    <BreadcrumbSeparator />
    <BreadcrumbItem>{section ? <BreadcrumbLink render={<Link href={base} />} className="max-w-[120px] truncate">{name}</BreadcrumbLink> : <BreadcrumbPage className="max-w-[120px] truncate">{name}</BreadcrumbPage>}</BreadcrumbItem>
    {section && <><BreadcrumbSeparator /><BreadcrumbItem><BreadcrumbPage className="capitalize">{section}</BreadcrumbPage></BreadcrumbItem></>}
  </>
}

export function AppHeader({ orgId }: AppHeaderProps) {
  const { organization } = useOrganization()
  const { workspaceId } = useParams<{ workspaceId?: string }>()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const orgName = organization?.name ?? '…'
  const workspacesHref = `/orgs/${orgId}/workspaces`

  return <TooltipProvider delay={300}>
    <header className="flex h-14 shrink-0 items-center gap-3 px-3 sm:px-5">
      <SidebarTrigger className="md:hidden" />
      <Breadcrumb className="min-w-0 flex-1">
        <BreadcrumbList className="flex-nowrap overflow-hidden">
          <BreadcrumbItem><BreadcrumbLink render={<Link href={workspacesHref} />} className="shrink-0 opacity-40 hover:opacity-90"><AppriseLogo className="h-4 w-auto brightness-0 invert" /><span className="sr-only">Apprise</span></BreadcrumbLink></BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem><BreadcrumbPage className="max-w-[100px] truncate text-muted">{orgName}</BreadcrumbPage></BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>{workspaceId ? <BreadcrumbLink render={<Link href={workspacesHref} />}>Workspaces</BreadcrumbLink> : <BreadcrumbPage>Workspaces</BreadcrumbPage>}</BreadcrumbItem>
          {workspaceId && <WorkspaceBreadcrumbItems workspaceId={workspaceId} orgId={orgId} />}
        </BreadcrumbList>
      </Breadcrumb>
      <div className="flex shrink-0 items-center gap-3">{workspaceId && <WorkspaceLiveStatus />}<div className="flex items-center gap-0.5"><HeaderIconButton label="Help"><IconHelp /></HeaderIconButton>{workspaceId && <HeaderIconButton label="Workspace settings" onClick={() => setSettingsOpen(true)}><IconSettings /></HeaderIconButton>}<HeaderIconButton label="Notifications"><IconNotifications /></HeaderIconButton></div></div>
      {workspaceId && <WorkspaceSettingsModal workspaceId={workspaceId} open={settingsOpen} onOpenChange={setSettingsOpen} />}
    </header>
  </TooltipProvider>
}
