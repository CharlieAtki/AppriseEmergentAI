import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useUpdateAgentWorkspacesWorkspaceIdAgentsAgentIdPatch,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
} from '@/api/generated/agents/agents'
import type { AgentResponse } from '@/api/generated/model'
import { toast } from 'sonner'

const REACTIVATE_TOAST_DURATION_MS = 4000

export function useAgentReactivate(workspaceId: string) {
  const queryClient = useQueryClient()

  const { mutate, isPending } = useUpdateAgentWorkspacesWorkspaceIdAgentsAgentIdPatch({
    mutation: {
      onSuccess: (response) => {
        const queryKey = getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey(workspaceId)
        queryClient.setQueryData<AgentResponse[]>(queryKey, (old) =>
          old ? old.map((a) => a.id === response.id ? { ...a, status: response.status } : a) : old
        )
        toast.success('Agent reactivated', { description: response.name, duration: REACTIVATE_TOAST_DURATION_MS })
      },
    },
  })

  const reactivateAgent = useCallback(
    (agentId: string) => {
      mutate({ workspaceId, agentId, data: { status: 'active' } })
    },
    [mutate, workspaceId],
  )

  return { reactivateAgent, isPending }
}
