'use client'

import { use } from 'react'
import { AppSidebar } from '@/components/layout/AppSidebar'
import { AppHeader } from '@/components/layout/AppHeader'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'

export default function OrgLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ orgId: string }>
}) {
  const { orgId } = use(params)

  return (
    <SidebarProvider defaultOpen>
      <AppSidebar orgId={orgId} />
      <SidebarInset>
        <AppHeader orgId={orgId} />
        <main className="flex-1 overflow-auto">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  )
}
