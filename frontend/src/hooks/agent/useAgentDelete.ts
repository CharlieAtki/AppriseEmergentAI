import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useDeleteAgentWorkspacesWorkspaceIdAgentsAgentIdDelete,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
} from '@/api/generated/agents/agents'
import type { AgentResponse } from '@/api/generated/model'
import { useToastStore } from '@/stores/toast'
import { clearAgentDeletePending, markAgentDeletePending } from './pendingAgentDeletes'

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
          toast({ title: 'Failed to delete agent', description: agent.name, variant: 'error' })
        } finally {
          clearAgentDeletePending(workspaceId)
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
          clearAgentDeletePending(workspaceId)
          queryClient.setQueryData<AgentResponse[]>(queryKey, (current) =>
            current ? insertAt(current, agent, originalIndex) : snapshot
          )
          dismiss(toastId)
        },
      })
    },
    [queryClient, mutateAsync, toast, dismiss, workspaceId]
  )

  return { deleteAgent }
}
