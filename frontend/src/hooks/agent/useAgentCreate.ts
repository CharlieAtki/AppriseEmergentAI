import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useCreateAgentWorkspacesWorkspaceIdAgentsPost,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
} from '@/api/generated/agents/agents'
import type { AgentResponse } from '@/api/generated/model'
import { useToastStore } from '@/stores/toast'

const CREATE_TOAST_DURATION_MS = 5000

export function useAgentCreate(workspaceId: string) {
  const queryClient = useQueryClient()
  const { toast, dismiss } = useToastStore()

  const { mutate, isPending } = useCreateAgentWorkspacesWorkspaceIdAgentsPost({
    mutation: {
      onSuccess: (response) => {
        const queryKey = getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey(workspaceId)
        queryClient.setQueryData<AgentResponse[]>(queryKey, (old) =>
          old ? [...old, response] : old
        )
        const toastId = crypto.randomUUID()
        toast({
          id: toastId,
          title: 'Agent spawned',
          description: response.name,
          variant: 'success',
          duration: CREATE_TOAST_DURATION_MS,
        })
        window.setTimeout(() => dismiss(toastId), CREATE_TOAST_DURATION_MS)
      },
    },
  })

  const createAgent = useCallback(
    (name: string, options?: { onSuccess?: () => void }) => {
      mutate(
        { workspaceId, data: { name } },
        options?.onSuccess !== undefined ? { onSuccess: options.onSuccess } : undefined,
      )
    },
    [mutate, workspaceId],
  )

  return { createAgent, isPending }
}
