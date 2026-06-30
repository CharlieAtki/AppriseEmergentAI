import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useDeleteAgentWorkspacesWorkspaceIdAgentsAgentIdDelete,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
  type listAgentsWorkspacesWorkspaceIdAgentsGetResponse,
} from '@/api/generated/agents/agents'
import type { AgentResponse } from '@/api/generated/fastAPI.schemas'
import { useToastStore } from '@/stores/toast'

export const DELETE_UNDO_DURATION_MS = 5000

function insertAt<T>(list: T[], item: T, index: number): T[] {
  const next = [...list]
  next.splice(Math.max(0, Math.min(index, next.length)), 0, item)
  return next
}

export function useAgentDelete(workspaceId: string) {
  const queryClient = useQueryClient()
  const { toast, dismiss } = useToastStore()
  const { mutateAsync } = useDeleteAgentWorkspacesWorkspaceIdAgentsAgentIdDelete()

  const deleteAgent = useCallback(
    (agent: AgentResponse) => {
      const queryKey = getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey(workspaceId)
      const snapshot = queryClient.getQueryData<listAgentsWorkspacesWorkspaceIdAgentsGetResponse>(queryKey)
      const originalIndex = snapshot?.status === 200
        ? snapshot.data.findIndex((a) => a.id === agent.id)
        : -1

      queryClient.setQueryData<listAgentsWorkspacesWorkspaceIdAgentsGetResponse>(queryKey, (old) =>
        old?.status === 200 ? { ...old, data: old.data.filter((a) => a.id !== agent.id) } : old
      )

      const toastId = crypto.randomUUID()

      const timeoutId = window.setTimeout(async () => {
        try {
          await mutateAsync({ workspaceId, agentId: agent.id })
          queryClient.setQueryData<listAgentsWorkspacesWorkspaceIdAgentsGetResponse>(queryKey, (current) =>
            current?.status === 200
              ? { ...current, data: current.data.filter((a) => a.id !== agent.id) }
              : current
          )
        } catch {
          queryClient.setQueryData<listAgentsWorkspacesWorkspaceIdAgentsGetResponse>(queryKey, (current) =>
            current?.status === 200
              ? { ...current, data: insertAt(current.data, agent, originalIndex) }
              : snapshot
          )
          toast({ title: 'Failed to delete agent', description: agent.name, variant: 'error' })
        } finally {
          dismiss(toastId)
        }
      }, DELETE_UNDO_DURATION_MS)

      toast({
        id: toastId,
        title: 'Agent deleted',
        description: agent.name,
        variant: 'success',
        duration: DELETE_UNDO_DURATION_MS,
        undoAction: () => {
          clearTimeout(timeoutId)
          queryClient.setQueryData<listAgentsWorkspacesWorkspaceIdAgentsGetResponse>(queryKey, (current) =>
            current?.status === 200
              ? { ...current, data: insertAt(current.data, agent, originalIndex) }
              : snapshot
          )
          dismiss(toastId)
        },
      })
    },
    [queryClient, mutateAsync, toast, dismiss, workspaceId]
  )

  return { deleteAgent }
}
