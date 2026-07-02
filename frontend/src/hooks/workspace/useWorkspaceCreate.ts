import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useCreateWorkspaceWorkspacesPost,
  getListWorkspacesWorkspacesGetQueryKey,
} from '@/api/generated/workspaces/workspaces'
import type { WorkspaceResponse } from '@/api/generated/model'
import { useToastStore } from '@/stores/toast'

const CREATE_TOAST_DURATION_MS = 5000

export function useWorkspaceCreate() {
  const queryClient = useQueryClient()
  const { toast, dismiss } = useToastStore()

  const { mutate, isPending } = useCreateWorkspaceWorkspacesPost({
    mutation: {
      onSuccess: (response) => {
        const queryKey = getListWorkspacesWorkspacesGetQueryKey()
        queryClient.setQueryData<WorkspaceResponse[]>(queryKey, (old) =>
          old ? [...old, response] : old
        )
        const toastId = crypto.randomUUID()
        toast({ id: toastId, title: 'Workspace created', description: response.name, variant: 'success', duration: CREATE_TOAST_DURATION_MS })
        window.setTimeout(() => dismiss(toastId), CREATE_TOAST_DURATION_MS)
      },
    },
  })

  const createWorkspace = useCallback(
    (name: string, options?: { onSuccess?: () => void }) => {
      mutate(
        { data: { name } },
        options?.onSuccess !== undefined ? { onSuccess: options.onSuccess } : undefined,
      )
    },
    [mutate],
  )

  return { createWorkspace, isPending }
}
