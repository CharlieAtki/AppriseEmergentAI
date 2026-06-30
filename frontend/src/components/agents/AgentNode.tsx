'use client'

import { memo, useState } from 'react'
import { type NodeProps } from '@xyflow/react'
import { motion, type MotionStyle } from 'framer-motion'
import { format } from 'date-fns'
import { AgentAvatar } from './AgentAvatar'
import { AgentInfoPopover } from './AgentInfoPopover'
import { EditAgentDialog } from './EditAgentDialog'
import { DeleteAgentDialog } from './DeleteAgentDialog'
import { Badge } from '@/components/ui/Badge'
import { IconEdit, IconActivate, IconDeactivate, IconDelete } from '@/lib/icons'
import { useAgentDelete } from '@/hooks/agent/useAgentDelete'
import { getAgentRingBorderClass, getAgentAccentVar } from '@/lib/agentColour'
import type { AgentResponse } from '@/api/generated/fastAPI.schemas'

type AgentNodeData = AgentResponse & {
  onDeactivate: (id: string) => void
  onReactivate: (id: string) => void
}

function AgentNodeInner({ data: rawData }: NodeProps) {
  const data = rawData as unknown as AgentNodeData
  const [editOpen, setEditOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  const { deleteAgent } = useAgentDelete(data.workspace_id)
  const ringBorder = getAgentRingBorderClass(data.id)
  const accentStyle = { '--agent-accent': getAgentAccentVar(data.id) } as unknown as MotionStyle

  const topSkills = data.skills
    ? Object.entries(data.skills)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 3)
    : []

  const agent = data as unknown as AgentResponse

  return (
    <>
      <motion.div
        initial={{ opacity: 0, scale: 0.88 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: 'spring', damping: 28, stiffness: 340 }}
        style={accentStyle}
        className="agent-node nopan nodrag w-64 rounded-xl border border-border bg-surface shadow-lg"
      >
        {/* Body */}
        <div className="p-3">
          {/* Header */}
          <div className="flex items-center gap-2.5">
            <div className="relative shrink-0">
              {data.status === 'active' && (
                <motion.span
                  className={`absolute inset-0 rounded-md border ${ringBorder}`}
                  animate={{ scale: [1, 1.6], opacity: [0.5, 0] }}
                  transition={{ duration: 2, repeat: Infinity, ease: 'easeOut', repeatDelay: 0.5 }}
                />
              )}
              <AgentAvatar id={data.id} name={data.name} size="md" />
            </div>

            <div className="min-w-0 flex-1">
              <p className="text-title font-semibold text-foreground leading-tight">{data.name}</p>
              <div className="mt-0.5">
                <Badge status={data.status} />
              </div>
            </div>
          </div>

          {/* Skill bars */}
          {topSkills.length > 0 && (
            <div className="mt-2.5 space-y-1.5 border-t border-border-subtle pt-2.5">
              {topSkills.map(([skill, value]) => (
                <div key={skill} className="flex items-center gap-2">
                  <span className="w-14 truncate text-caption text-muted">{skill}</span>
                  <div className="h-1 flex-1 overflow-hidden rounded-full bg-elevated">
                    <motion.div
                      className="h-full rounded-full bg-brand-primary"
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.min(value * 100, 100)}%` }}
                      transition={{ duration: 0.6, delay: 0.15, ease: [0.4, 0, 0.2, 1] }}
                    />
                  </div>
                  <span className="w-6 text-right text-caption text-muted">
                    {Math.round(value * 100)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Metadata */}
          <div className={`space-y-1 ${topSkills.length > 0 ? 'mt-2' : 'mt-2.5 border-t border-border-subtle pt-2.5'}`}>
            <div className="flex items-center justify-between">
              <span className="text-caption text-muted">Influence</span>
              <span className="text-caption font-medium text-secondary">
                {data.influence != null ? data.influence.toFixed(2) : '—'}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-caption text-muted">Created</span>
              <span className="text-caption font-medium text-secondary">
                {format(new Date(data.created_at), 'd MMM yyyy')}
              </span>
            </div>
          </div>
        </div>

        {/* Action strip — sits below a divider, outside the body padding */}
        <div className="flex items-center gap-0.5 border-t border-border-subtle px-2 py-1.5">
          <AgentInfoPopover agent={agent} />

          <button
            onClick={(e) => { e.stopPropagation(); setEditOpen(true) }}
            aria-label="Edit agent"
            className="rounded-md p-1.5 text-muted transition-colors hover:bg-hover hover:text-foreground"
          >
            <IconEdit size={13} />
          </button>

          {data.status === 'active' ? (
            <button
              onClick={(e) => { e.stopPropagation(); data.onDeactivate(data.id) }}
              aria-label="Deactivate agent"
              className="rounded-md p-1.5 text-muted transition-colors hover:bg-error/10 hover:text-error"
            >
              <IconDeactivate size={13} />
            </button>
          ) : (
            <button
              onClick={(e) => { e.stopPropagation(); data.onReactivate(data.id) }}
              aria-label="Reactivate agent"
              className="rounded-md p-1.5 text-muted transition-colors hover:bg-success/10 hover:text-success"
            >
              <IconActivate size={13} />
            </button>
          )}

          <button
            onClick={(e) => { e.stopPropagation(); setDeleteOpen(true) }}
            aria-label="Delete agent"
            className="ml-auto rounded-md p-1.5 text-muted transition-colors hover:bg-error/10 hover:text-error"
          >
            <IconDelete size={13} />
          </button>
        </div>

        {/* TODO: add ReactFlow Handles (source + target, all sides) in the same commit as edge connections */}
      </motion.div>

      <EditAgentDialog agent={agent} open={editOpen} onOpenChange={setEditOpen} />
      <DeleteAgentDialog
        agent={agent}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onConfirm={() => { setDeleteOpen(false); deleteAgent(agent) }}
      />
    </>
  )
}

export const AgentNode = memo(AgentNodeInner)
