import { useCallback } from 'react'
import { useToastStore, type ToastItem } from '@/stores/toast'

export function useAutoDismissToast() {
  const { toast, dismiss } = useToastStore()

  return useCallback(
    (item: Omit<ToastItem, 'id'> & { duration: number }) => {
      const toastId = crypto.randomUUID()
      toast({ ...item, id: toastId })
      window.setTimeout(() => dismiss(toastId), item.duration)
    },
    [toast, dismiss],
  )
}
