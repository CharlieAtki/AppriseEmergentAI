'use client'

import { use } from 'react'
import { useWorkspaceStream } from '@/hooks/workspace/useWorkspaceStream'

export default function WorkspaceLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ workspaceId: string }>
}) {
  const { workspaceId } = use(params)
  useWorkspaceStream(workspaceId)

  return <>{children}</>
}
