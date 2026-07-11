'use client'

import { useParams } from 'next/navigation'
import { DashboardGrid } from '@/components/dashboard/DashboardGrid'

export default function WorkspacePage() {
  const { workspaceId } = useParams<{ workspaceId: string }>()
  return <DashboardGrid workspaceId={workspaceId} />
}
