import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useCreateAgentWorkspacesWorkspaceIdAgentsPost,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
} from '@/api/generated/agents/agents'
import type { AgentResponse } from '@/api/generated/model'
import { toast } from 'sonner'

const CREATE_TOAST_DURATION_MS = 5000

export function useAgentCreate(workspaceId: string) {
  const queryClient = useQueryClient()

  const { mutate, isPending } = useCreateAgentWorkspacesWorkspaceIdAgentsPost({
    mutation: {
      onSuccess: (response) => {
        const queryKey = getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey(workspaceId)
        queryClient.setQueryData<AgentResponse[]>(queryKey, (old) =>
          old ? [...old, response] : [response]
        )
        toast.success('Agent spawned', { description: response.name, duration: CREATE_TOAST_DURATION_MS })
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
