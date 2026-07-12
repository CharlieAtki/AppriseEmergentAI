'use client'

import { motion, useReducedMotion } from 'framer-motion'
import { IconAdd } from '@/lib/icons'
import { useState } from 'react'
import { cardHover } from '@/lib/motion'
import { CreateWorkspaceDialog } from './CreateWorkspaceDialog'

interface NewWorkspaceCardProps {
  orgId: string
}

export function NewWorkspaceCard({ orgId }: NewWorkspaceCardProps) {
  const [open, setOpen] = useState(false)
  const shouldReduceMotion = useReducedMotion()

  return (
    <>
      <motion.button
        onClick={() => setOpen(true)}
        {...(!shouldReduceMotion && { whileHover: cardHover })}
        className="group flex h-full min-h-[9rem] w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-surface/50 transition-colors hover:border-brand-primary hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary"
      >
        <span className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-elevated transition-colors group-hover:border-brand-primary group-hover:bg-brand-primary/10 group-hover:text-brand-primary text-muted">
          <IconAdd size={18} />
        </span>
        <div className="text-center">
          <p className="text-body font-medium text-muted group-hover:text-brand-primary transition-colors">New workspace</p>
          <p className="text-caption text-muted">Create a new environment</p>
        </div>
      </motion.button>

      <CreateWorkspaceDialog orgId={orgId} open={open} onOpenChange={setOpen} />
    </>
  )
}
