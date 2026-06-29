'use client'

import { use } from 'react'
import { AppSidebar } from '@/components/layout/AppSidebar'
import { AppHeader } from '@/components/layout/AppHeader'

export default function OrgLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ orgId: string }>
}) {
  const { orgId } = use(params)

  return (
    <div className="flex min-h-screen">
      <AppSidebar orgId={orgId} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <AppHeader orgId={orgId} />
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  )
}
