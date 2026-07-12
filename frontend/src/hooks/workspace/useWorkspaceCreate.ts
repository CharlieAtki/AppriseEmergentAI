import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useCreateWorkspaceWorkspacesPost,
  getListWorkspacesWorkspacesGetQueryKey,
} from '@/api/generated/workspaces/workspaces'
import type { WorkspaceResponse } from '@/api/generated/model'
import { toast } from 'sonner'

const CREATE_TOAST_DURATION_MS = 5000

export function useWorkspaceCreate() {
  const queryClient = useQueryClient()

  const { mutate, isPending } = useCreateWorkspaceWorkspacesPost({
    mutation: {
      onSuccess: (response) => {
        const queryKey = getListWorkspacesWorkspacesGetQueryKey()
        queryClient.setQueryData<WorkspaceResponse[]>(queryKey, (old) =>
          old ? [...old, response] : [response]
        )
        toast.success('Workspace created', { description: response.name, duration: CREATE_TOAST_DURATION_MS })
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
