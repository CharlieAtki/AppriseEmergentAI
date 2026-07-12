import { DashboardGrid } from '@/components/dashboard/DashboardGrid'

export default async function WorkspacePage({
  params,
}: {
  params: Promise<{ workspaceId: string }>
}) {
  const { workspaceId } = await params
  return <DashboardGrid workspaceId={workspaceId} />
}
