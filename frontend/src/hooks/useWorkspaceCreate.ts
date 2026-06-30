import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useCreateWorkspaceWorkspacesPost,
  getListWorkspacesWorkspacesGetQueryKey,
  type listWorkspacesWorkspacesGetResponse,
} from '@/api/generated/workspaces/workspaces'
import { useToastStore } from '@/stores/toast'

const CREATE_TOAST_DURATION_MS = 5000

export function useWorkspaceCreate() {
  const queryClient = useQueryClient()
  const { toast, dismiss } = useToastStore()

  const { mutate, isPending } = useCreateWorkspaceWorkspacesPost({
    mutation: {
      onSuccess: (response) => {
        if (response.status !== 201) return
        const queryKey = getListWorkspacesWorkspacesGetQueryKey()
        queryClient.setQueryData<listWorkspacesWorkspacesGetResponse>(queryKey, (old) =>
          old ? { ...old, data: [...old.data, response.data] } : old
        )
        const toastId = crypto.randomUUID()
        toast({ id: toastId, title: 'Workspace created', description: response.data.name, variant: 'success', duration: CREATE_TOAST_DURATION_MS })
        window.setTimeout(() => dismiss(toastId), CREATE_TOAST_DURATION_MS)
      },
    },
  })

  const createWorkspace = useCallback(
    (name: string, options?: { onSuccess?: () => void }) => {
      mutate({ data: { name } }, { onSuccess: options?.onSuccess })
    },
    [mutate],
  )

  return { createWorkspace, isPending }
}
