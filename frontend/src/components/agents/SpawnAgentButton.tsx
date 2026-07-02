'use client'

import { motion } from 'framer-motion'
import { IconAgent } from '@/lib/icons'

interface SpawnAgentButtonProps {
  onClick: () => void
}

export function SpawnAgentButton({ onClick }: SpawnAgentButtonProps) {
  return (
    <motion.button
      onClick={onClick}
      initial={{ y: 16, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      whileHover={{ scale: 1.04, transition: { type: 'spring', damping: 30, stiffness: 400 } }}
      whileTap={{ scale: 0.97 }}
      transition={{ delay: 0.3, duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
      className="spawn-agent-btn flex items-center gap-2 rounded-lg bg-brand-primary px-4 py-2 text-body font-medium text-background transition-colors hover:bg-brand-hover"
    >
      <IconAgent size={16} />
      Spawn agent
    </motion.button>
  )
}
