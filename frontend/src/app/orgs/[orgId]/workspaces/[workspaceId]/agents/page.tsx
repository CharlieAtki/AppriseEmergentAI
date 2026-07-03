import { AgentGraph } from '@/components/agents/AgentGraph'

export default async function AgentsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>
}) {
  const { workspaceId } = await params
  return <AgentGraph workspaceId={workspaceId} />
}
