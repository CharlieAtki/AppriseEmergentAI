import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useUpdateAgentWorkspacesWorkspaceIdAgentsAgentIdPatch,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
} from '@/api/generated/agents/agents'
import type { AgentResponse } from '@/api/generated/model'
import { useToastStore } from '@/stores/toast'

const REACTIVATE_TOAST_DURATION_MS = 4000

export function useAgentReactivate(workspaceId: string) {
  const queryClient = useQueryClient()
  const { toast, dismiss } = useToastStore()

  const { mutate, isPending } = useUpdateAgentWorkspacesWorkspaceIdAgentsAgentIdPatch({
    mutation: {
      onSuccess: (response) => {
        const queryKey = getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey(workspaceId)
        queryClient.setQueryData<AgentResponse[]>(queryKey, (old) =>
          old ? old.map((a) => a.id === response.id ? { ...a, status: response.status } : a) : old
        )
        const toastId = crypto.randomUUID()
        toast({
          id: toastId,
          title: 'Agent reactivated',
          description: response.name,
          variant: 'success',
          duration: REACTIVATE_TOAST_DURATION_MS,
        })
        window.setTimeout(() => dismiss(toastId), REACTIVATE_TOAST_DURATION_MS)
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
