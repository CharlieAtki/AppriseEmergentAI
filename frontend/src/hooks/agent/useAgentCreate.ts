import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useCreateAgentWorkspacesWorkspaceIdAgentsPost,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
  type listAgentsWorkspacesWorkspaceIdAgentsGetResponse,
} from '@/api/generated/agents/agents'
import { useToastStore } from '@/stores/toast'

const CREATE_TOAST_DURATION_MS = 5000

export function useAgentCreate(workspaceId: string) {
  const queryClient = useQueryClient()
  const { toast, dismiss } = useToastStore()

  const { mutate, isPending } = useCreateAgentWorkspacesWorkspaceIdAgentsPost({
    mutation: {
      onSuccess: (response) => {
        if (response.status !== 201) return
        const queryKey = getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey(workspaceId)
        queryClient.setQueryData<listAgentsWorkspacesWorkspaceIdAgentsGetResponse>(queryKey, (old) => {
          if (!old || old.status !== 200) return old
          return { ...old, data: [...old.data, response.data] }
        })
        const toastId = crypto.randomUUID()
        toast({
          id: toastId,
          title: 'Agent spawned',
          description: response.data.name,
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
