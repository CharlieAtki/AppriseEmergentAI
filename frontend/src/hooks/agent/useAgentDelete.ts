import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useDeleteAgentWorkspacesWorkspaceIdAgentsAgentIdDelete,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
} from '@/api/generated/agents/agents'
import type { AgentResponse } from '@/api/generated/model'
import { toast } from 'sonner'
import { clearAgentDeletePending, markAgentDeletePending } from './pendingAgentDeletes'

export const DELETE_UNDO_DURATION_MS = 5000

function insertAt<T>(list: T[], item: T, index: number): T[] {
  const next = [...list]
  next.splice(Math.max(0, Math.min(index, next.length)), 0, item)
  return next
}

export function useAgentDelete(workspaceId: string) {
  const queryClient = useQueryClient()
  const { mutateAsync } = useDeleteAgentWorkspacesWorkspaceIdAgentsAgentIdDelete()

  const deleteAgent = useCallback(
    (agent: AgentResponse) => {
      const queryKey = getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey(workspaceId)
      const snapshot = queryClient.getQueryData<AgentResponse[]>(queryKey)
      const originalIndex = snapshot?.findIndex((a) => a.id === agent.id) ?? -1

      queryClient.setQueryData<AgentResponse[]>(queryKey, (old) =>
        old ? old.filter((a) => a.id !== agent.id) : old
      )

      markAgentDeletePending(workspaceId)

      const toastId = crypto.randomUUID()

      const timeoutId = window.setTimeout(async () => {
        try {
          await mutateAsync({ workspaceId, agentId: agent.id })
          queryClient.setQueryData<AgentResponse[]>(queryKey, (current) =>
            current ? current.filter((a) => a.id !== agent.id) : current
          )
        } catch {
          queryClient.setQueryData<AgentResponse[]>(queryKey, (current) =>
            current ? insertAt(current, agent, originalIndex) : snapshot
          )
          toast.error('Failed to delete agent', { description: agent.name })
        } finally {
          clearAgentDeletePending(workspaceId)
          toast.dismiss(toastId)
        }
      }, DELETE_UNDO_DURATION_MS)

      toast.success('Agent deleted', {
        id: toastId,
        description: agent.name,
        duration: DELETE_UNDO_DURATION_MS,
        action: {
          label: 'Undo',
          onClick: () => {
            clearTimeout(timeoutId)
            clearAgentDeletePending(workspaceId)
            queryClient.setQueryData<AgentResponse[]>(queryKey, (current) =>
              current ? insertAt(current, agent, originalIndex) : snapshot
            )
            toast.dismiss(toastId)
          },
        },
      })
    },
    [queryClient, mutateAsync, workspaceId]
  )

  return { deleteAgent }
}
