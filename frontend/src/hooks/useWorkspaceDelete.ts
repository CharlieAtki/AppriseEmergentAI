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

export function useWorkspaceDelete() {
  const queryClient = useQueryClient()
  const { toast, dismiss } = useToastStore()
  const { mutateAsync } = useDeleteWorkspaceWorkspacesWorkspaceIdDelete()

  const deleteWorkspace = useCallback(
    (workspace: WorkspaceResponse) => {
      const queryKey = getListWorkspacesWorkspacesGetQueryKey()
      const snapshot = queryClient.getQueryData<listWorkspacesWorkspacesGetResponse>(queryKey)

      // Optimistically remove the card immediately
      queryClient.setQueryData<listWorkspacesWorkspacesGetResponse>(queryKey, (old) =>
        old ? { ...old, data: old.data.filter((w) => w.id !== workspace.id) } : old
      )

      const toastId = crypto.randomUUID()

      const timeoutId = window.setTimeout(async () => {
        try {
          await mutateAsync({ workspaceId: workspace.id })
          await queryClient.invalidateQueries({ queryKey })
        } catch {
          // Restore the card on failure
          queryClient.setQueryData(queryKey, snapshot)
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
        duration: DELETE_UNDO_DURATION_MS,
        undoAction: () => {
          clearTimeout(timeoutId)
          queryClient.setQueryData(queryKey, snapshot)
          dismiss(toastId)
        },
      })
    },
    [queryClient, mutateAsync, toast, dismiss]
  )

  return { deleteWorkspace }
}
