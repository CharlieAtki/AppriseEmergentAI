'use client'

import * as Toast from '@radix-ui/react-toast'
import { AnimatePresence, motion } from 'framer-motion'
import { X, RotateCcw } from 'lucide-react'
import { useToastStore } from '@/stores/toast'

const variantStyles: Record<string, string> = {
  success: 'border-success/30',
  error:   'border-error/30',
  default: 'border-border',
}

const dotStyles: Record<string, string> = {
  success: 'bg-success',
  error:   'bg-error',
  default: 'bg-brand-primary',
}

const barStyles: Record<string, string> = {
  success: 'bg-success',
  error:   'bg-error',
  default: 'bg-brand-primary',
}

function CountdownBar({ variant, duration }: { variant: string; duration: number }) {
  return (
    <motion.div
      className={`absolute bottom-0 left-0 h-[2px] w-full origin-left rounded-full ${barStyles[variant]}`}
      initial={{ scaleX: 1 }}
      animate={{ scaleX: 0 }}
      transition={{ duration: duration / 1000, ease: 'linear' }}
    />
  )
}

export function Toaster() {
  const { toasts, dismiss } = useToastStore()

  return (
    <Toast.Provider swipeDirection="down" duration={4000}>
      <AnimatePresence mode="sync">
        {toasts.map((t) => (
          <Toast.Root
            key={t.id}
            open
            forceMount
            duration={t.undoAction ? Infinity : 4000}
            onOpenChange={(open) => { if (!open) dismiss(t.id) }}
            asChild
          >
            <motion.li
              layout
              initial={{ opacity: 0, y: 20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 12, scale: 0.94 }}
              transition={{ type: 'spring', damping: 26, stiffness: 360 }}
              className={`relative flex items-start gap-3 overflow-hidden rounded-xl border bg-surface p-4 shadow-xl ${variantStyles[t.variant ?? 'default']}`}
            >
              <span className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${dotStyles[t.variant ?? 'default']}`} />

              <div className="flex-1 min-w-0">
                <Toast.Title className="text-body font-medium text-foreground">
                  {t.title}
                </Toast.Title>
                {t.description && (
                  <Toast.Description className="mt-0.5 text-caption text-muted">
                    {t.description}
                  </Toast.Description>
                )}
              </div>

              <div className="flex shrink-0 items-center gap-1">
                {t.undoAction && (
                  <motion.div
                    initial={{ opacity: 0, x: 4 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.12, duration: 0.2 }}
                  >
                    <Toast.Action altText="Undo" asChild>
                      <button
                        onClick={t.undoAction}
                        className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-label font-medium text-foreground transition-colors hover:bg-elevated"
                      >
                        <RotateCcw size={11} />
                        Undo
                      </button>
                    </Toast.Action>
                  </motion.div>
                )}
                <Toast.Close asChild>
                  <button
                    aria-label="Dismiss"
                    className="rounded-md p-1 text-muted transition-colors hover:text-foreground"
                  >
                    <X size={13} />
                  </button>
                </Toast.Close>
              </div>

              {t.undoAction && <CountdownBar variant={t.variant ?? 'default'} duration={t.duration ?? 5000} />}
            </motion.li>
          </Toast.Root>
        ))}
      </AnimatePresence>

      <Toast.Viewport className="fixed bottom-6 left-1/2 z-50 flex w-full max-w-sm -translate-x-1/2 flex-col gap-2 outline-none" />
    </Toast.Provider>
  )
}
