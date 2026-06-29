'use client'

import { motion, AnimatePresence } from 'framer-motion'
import type { WorkspaceResponse } from '@/api/generated/fastAPI.schemas'
import { WorkspaceCard } from './WorkspaceCard'
import { NewWorkspaceCard } from './NewWorkspaceCard'
import { cardEntrance } from '@/lib/motion'

interface WorkspaceGridProps {
  workspaces: WorkspaceResponse[]
  orgId: string
  view: 'grid' | 'list'
}

export function WorkspaceGrid({ workspaces, orgId, view }: WorkspaceGridProps) {
  const gridClass = view === 'grid'
    ? 'grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3'
    : 'flex flex-col gap-2'

  return (
    <div className={gridClass}>
      <motion.div
        key="new-workspace"
        custom={0}
        initial="hidden"
        animate="visible"
        variants={cardEntrance}
      >
        <NewWorkspaceCard orgId={orgId} />
      </motion.div>

      <AnimatePresence>
        {workspaces.map((workspace, i) => (
          <motion.div
            key={workspace.id}
            custom={i + 1}
            initial="hidden"
            animate="visible"
            exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.15 } }}
            variants={cardEntrance}
          >
            <WorkspaceCard workspace={workspace} orgId={orgId} view={view} />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
