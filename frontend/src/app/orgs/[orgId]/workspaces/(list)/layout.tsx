'use client'

import { use } from 'react'
import { Sidebar } from '@/components/layout/Sidebar'

export default function WorkspacesListLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ orgId: string }>
}) {
  const { orgId } = use(params)

  return (
    <div className="flex min-h-screen">
      <Sidebar orgId={orgId} />
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  )
}
