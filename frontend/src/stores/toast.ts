import { create } from 'zustand'

export type ToastVariant = 'default' | 'success' | 'error'

export interface ToastItem {
  id: string
  title: string
  description?: string
  variant?: ToastVariant
  undoAction?: () => void
  /** Duration in ms for the countdown bar. Only meaningful when undoAction is present. */
  duration?: number
}

interface ToastStore {
  toasts: ToastItem[]
  toast: (item: Omit<ToastItem, 'id'> & { id?: string }) => void
  dismiss: (id: string) => void
}

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  toast: (item) =>
    set((state) => ({
      toasts: [...state.toasts, { ...item, id: item.id ?? crypto.randomUUID() }],
    })),
  dismiss: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    })),
}))
