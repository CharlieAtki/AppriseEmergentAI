'use client'

import { use } from 'react'
import { useWorkspaceStream } from '@/hooks/useWorkspaceStream'

export default function WorkspaceLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  useWorkspaceStream(id)
  return <>{children}</>
}
