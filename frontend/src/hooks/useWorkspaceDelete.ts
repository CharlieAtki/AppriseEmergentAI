import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useDeleteWorkspaceWorkspacesWorkspaceIdDelete,
  getListWorkspacesWorkspacesGetQueryKey,
  type listWorkspacesWorkspacesGetResponse,
} from '@/api/generated/workspaces/workspaces'
import type { WorkspaceResponse } from '@/api/generated/fastAPI.schemas'
import { useToastStore } from '@/stores/toast'

export const DELETE_UNDO_DURATION_MS = 5000

function insertAt<T>(list: T[], item: T, index: number): T[] {
  const next = [...list]
  next.splice(Math.max(0, Math.min(index, next.length)), 0, item)
  return next
}

export function useWorkspaceDelete() {
  const queryClient = useQueryClient()
  const { toast, dismiss } = useToastStore()
  const { mutateAsync } = useDeleteWorkspaceWorkspacesWorkspaceIdDelete()

  const deleteWorkspace = useCallback(
    (workspace: WorkspaceResponse) => {
      const queryKey = getListWorkspacesWorkspacesGetQueryKey()
      const snapshot = queryClient.getQueryData<listWorkspacesWorkspacesGetResponse>(queryKey)
      const originalIndex = snapshot?.data.findIndex((w) => w.id === workspace.id) ?? -1

      // Optimistically remove the card immediately
      queryClient.setQueryData<listWorkspacesWorkspacesGetResponse>(queryKey, (old) =>
        old ? { ...old, data: old.data.filter((w) => w.id !== workspace.id) } : old
      )

      const toastId = crypto.randomUUID()

      const timeoutId = window.setTimeout(async () => {
        try {
          await mutateAsync({ workspaceId: workspace.id })
          // Confirm the optimistic removal without a refetch — a full invalidation here
          // would show server state mid-flight while other pending deletes haven't committed yet.
          queryClient.setQueryData<listWorkspacesWorkspacesGetResponse>(queryKey, (current) =>
            current ? { ...current, data: current.data.filter((w) => w.id !== workspace.id) } : current
          )
        } catch {
          // Restore only this workspace into current cache state on failure
          queryClient.setQueryData<listWorkspacesWorkspacesGetResponse>(queryKey, (current) =>
            current ? { ...current, data: insertAt(current.data, workspace, originalIndex) } : snapshot
          )
          toast({
            title: 'Failed to delete workspace',
            description: workspace.name,
            variant: 'error',
          })
        } finally {
          dismiss(toastId)
        }
      }, DELETE_UNDO_DURATION_MS)

      toast({
        id: toastId,
        title: 'Workspace deleted',
        description: workspace.name,
        variant: 'success',
        duration: DELETE_UNDO_DURATION_MS,
        undoAction: () => {
          clearTimeout(timeoutId)
          // Insert only this workspace back at its original position in the current list
          queryClient.setQueryData<listWorkspacesWorkspacesGetResponse>(queryKey, (current) =>
            current ? { ...current, data: insertAt(current.data, workspace, originalIndex) } : snapshot
          )
          dismiss(toastId)
        },
      })
    },
    [queryClient, mutateAsync, toast, dismiss]
  )

  return { deleteWorkspace }
}
