import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useUpdateAgentWorkspacesWorkspaceIdAgentsAgentIdPatch,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
} from '@/api/generated/agents/agents'
import type { AgentResponse } from '@/api/generated/model'
import { useAutoDismissToast } from '@/hooks/useAutoDismissToast'

const DEACTIVATE_TOAST_DURATION_MS = 4000

export function useAgentDeactivate(workspaceId: string) {
  const queryClient = useQueryClient()
  const showToast = useAutoDismissToast()

  const { mutate, isPending } = useUpdateAgentWorkspacesWorkspaceIdAgentsAgentIdPatch({
    mutation: {
      onSuccess: (response) => {
        const queryKey = getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey(workspaceId)
        queryClient.setQueryData<AgentResponse[]>(queryKey, (old) =>
          old ? old.map((a) => a.id === response.id ? { ...a, status: response.status } : a) : old
        )
        showToast({
          title: 'Agent deactivated',
          description: response.name,
          variant: 'success',
          duration: DEACTIVATE_TOAST_DURATION_MS,
        })
      },
    },
  })

  const deactivateAgent = useCallback(
    (agentId: string) => {
      mutate({ workspaceId, agentId, data: { status: 'inactive' } })
    },
    [mutate, workspaceId],
  )

  return { deactivateAgent, isPending }
}
