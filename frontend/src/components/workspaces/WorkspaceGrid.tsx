'use client'

import { motion, AnimatePresence } from 'framer-motion'
import type { WorkspaceResponse } from '@/api/generated/fastAPI.schemas'
import { WorkspaceCard } from './WorkspaceCard'
import { cardEntrance } from '@/lib/motion'

interface WorkspaceGridProps {
  workspaces: WorkspaceResponse[]
  orgId: string
}

export function WorkspaceGrid({ workspaces, orgId }: WorkspaceGridProps) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <AnimatePresence>
        {workspaces.map((workspace, i) => (
          <motion.div
            key={workspace.id}
            custom={i}
            initial="hidden"
            animate="visible"
            exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.15 } }}
            variants={cardEntrance}
          >
            <WorkspaceCard workspace={workspace} orgId={orgId} />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
