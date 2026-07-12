import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useDeleteWorkspaceWorkspacesWorkspaceIdDelete,
  getListWorkspacesWorkspacesGetQueryKey,
} from '@/api/generated/workspaces/workspaces'
import type { WorkspaceResponse } from '@/api/generated/model'
import { toast } from 'sonner'

export const DELETE_UNDO_DURATION_MS = 5000

function insertAt<T>(list: T[], item: T, index: number): T[] {
  const next = [...list]
  next.splice(Math.max(0, Math.min(index, next.length)), 0, item)
  return next
}

export function useWorkspaceDelete() {
  const queryClient = useQueryClient()
  const { mutateAsync } = useDeleteWorkspaceWorkspacesWorkspaceIdDelete()

  const deleteWorkspace = useCallback(
    (workspace: WorkspaceResponse) => {
      const queryKey = getListWorkspacesWorkspacesGetQueryKey()
      const snapshot = queryClient.getQueryData<WorkspaceResponse[]>(queryKey)
      const originalIndex = snapshot?.findIndex((w) => w.id === workspace.id) ?? -1

      queryClient.setQueryData<WorkspaceResponse[]>(queryKey, (old) =>
        old ? old.filter((w) => w.id !== workspace.id) : old
      )

      const toastId = crypto.randomUUID()

      const timeoutId = window.setTimeout(async () => {
        try {
          await mutateAsync({ workspaceId: workspace.id })
          queryClient.setQueryData<WorkspaceResponse[]>(queryKey, (current) =>
            current ? current.filter((w) => w.id !== workspace.id) : current
          )
        } catch {
          queryClient.setQueryData<WorkspaceResponse[]>(queryKey, (current) =>
            current ? insertAt(current, workspace, originalIndex) : snapshot
          )
          toast.error('Failed to delete workspace', { description: workspace.name })
        } finally {
          toast.dismiss(toastId)
        }
      }, DELETE_UNDO_DURATION_MS)

      toast.success('Workspace deleted', {
        id: toastId,
        description: workspace.name,
        duration: DELETE_UNDO_DURATION_MS,
        action: {
          label: 'Undo',
          onClick: () => {
            clearTimeout(timeoutId)
            queryClient.setQueryData<WorkspaceResponse[]>(queryKey, (current) =>
              current ? insertAt(current, workspace, originalIndex) : snapshot
            )
            toast.dismiss(toastId)
          },
        },
      })
    },
    [queryClient, mutateAsync]
  )

  return { deleteWorkspace }
}
