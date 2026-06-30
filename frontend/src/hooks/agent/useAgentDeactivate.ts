import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useUpdateAgentWorkspacesWorkspaceIdAgentsAgentIdPatch,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
  type listAgentsWorkspacesWorkspaceIdAgentsGetResponse,
} from '@/api/generated/agents/agents'
import { AgentStatus } from '@/api/generated/fastAPI.schemas'
import { useToastStore } from '@/stores/toast'

const DEACTIVATE_TOAST_DURATION_MS = 4000

export function useAgentDeactivate(workspaceId: string) {
  const queryClient = useQueryClient()
  const { toast, dismiss } = useToastStore()

  const { mutate, isPending } = useUpdateAgentWorkspacesWorkspaceIdAgentsAgentIdPatch({
    mutation: {
      onSuccess: (response) => {
        if (response.status !== 200) return
        const queryKey = getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey(workspaceId)
        queryClient.setQueryData<listAgentsWorkspacesWorkspaceIdAgentsGetResponse>(queryKey, (old) => {
          if (!old || old.status !== 200) return old
          return {
            ...old,
            data: old.data.map((a) =>
              a.id === response.data.id ? { ...a, status: response.data.status } : a,
            ),
          }
        })
        const toastId = crypto.randomUUID()
        toast({
          id: toastId,
          title: 'Agent deactivated',
          description: response.data.name,
          variant: 'success',
          duration: DEACTIVATE_TOAST_DURATION_MS,
        })
        window.setTimeout(() => dismiss(toastId), DEACTIVATE_TOAST_DURATION_MS)
      },
    },
  })

  const deactivateAgent = useCallback(
    (agentId: string) => {
      mutate({ workspaceId, agentId, data: { status: AgentStatus.inactive } })
    },
    [mutate, workspaceId],
  )

  return { deactivateAgent, isPending }
}
