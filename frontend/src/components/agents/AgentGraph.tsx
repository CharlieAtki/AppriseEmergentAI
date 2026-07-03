'use client'

import '@xyflow/react/dist/style.css'

import { useState, useMemo, useCallback } from 'react'
import { ReactFlow, Background, Controls, type Node } from '@xyflow/react'
import { IconAgent, IconSearch } from '@/lib/icons'
import { useListAgentsWorkspacesWorkspaceIdAgentsGet } from '@/api/generated/agents/agents'
import { useAgentDeactivate } from '@/hooks/agent/useAgentDeactivate'
import { useAgentReactivate } from '@/hooks/agent/useAgentReactivate'
import { AgentNode } from './AgentNode'
import { SpawnAgentButton } from './SpawnAgentButton'
import { SpawnAgentDialog } from './SpawnAgentDialog'
import type { AgentResponse } from '@/api/generated/model'

// Must be defined at module scope — ReactFlow re-renders all nodes if nodeTypes
// is a new object reference on each render.
const nodeTypes = { agentNode: AgentNode }

function radialLayout(
  count: number,
  radius = 280,
  cx = 500,
  cy = 300,
): { x: number; y: number }[] {
  if (count === 0) return []
  if (count === 1) return [{ x: cx, y: cy }]
  return Array.from({ length: count }, (_, i) => {
    const angle = (2 * Math.PI * i) / count - Math.PI / 2
    return { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) }
  })
  // TODO: replace with connection-driven layout (dagre / ELK) when agent handoff edges are introduced
}

function agentsToNodes(
  agents: AgentResponse[],
  onDeactivate: (id: string) => void,
  onReactivate: (id: string) => void,
): Node[] {
  const sorted = [...agents].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )
  const positions = radialLayout(sorted.length)
  return sorted.map((agent, i) => ({
    id: agent.id,
    type: 'agentNode',
    position: positions[i] ?? { x: 0, y: 0 },
    // ReactFlow requires Record<string, unknown>; AgentResponse is cast at the node boundary.
    data: { ...agent, onDeactivate, onReactivate } as unknown as Record<string, unknown>,
    draggable: false,
  }))
}

interface AgentGraphProps {
  workspaceId: string
}

export function AgentGraph({ workspaceId }: AgentGraphProps) {
  const [spawnOpen, setSpawnOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  const { data: agentsResponse } = useListAgentsWorkspacesWorkspaceIdAgentsGet(workspaceId)
  const agents = agentsResponse ?? []
  const activeCount = agents.filter((a) => a.status === 'active').length

  const { deactivateAgent } = useAgentDeactivate(workspaceId)
  const { reactivateAgent } = useAgentReactivate(workspaceId)
  const handleDeactivate = useCallback((id: string) => deactivateAgent(id), [deactivateAgent])
  const handleReactivate = useCallback((id: string) => reactivateAgent(id), [reactivateAgent])

  const filteredAgents = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    return query === '' ? agents : agents.filter((a) => a.name.toLowerCase().includes(query))
  }, [agents, searchQuery])

  const nodes = useMemo<Node[]>(
    () => agentsToNodes(filteredAgents, handleDeactivate, handleReactivate),
    [filteredAgents, handleDeactivate, handleReactivate],
  )

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 items-start justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="font-display text-heading text-foreground">Agents</h1>
          <p className="mt-0.5 text-body text-muted">Emergent agents in this workspace.</p>
        </div>
        <span className="rounded-full bg-success/10 px-2.5 py-0.5 text-label font-medium text-success">
          {activeCount} active
        </span>
      </header>

      <div className="relative min-h-0 flex-1">
        {agents.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-border bg-surface">
              <IconAgent size={24} className="text-muted" />
            </div>
            <div>
              <p className="text-title font-semibold text-foreground">No agents yet</p>
              <p className="mt-1 text-body text-muted">Spawn the first agent to get started.</p>
            </div>
            <SpawnAgentButton onClick={() => setSpawnOpen(true)} />
          </div>
        ) : (
          <>
            <ReactFlow
              nodes={nodes}
              edges={[]}
              // TODO: populate edges from agent handoff topology (Phase 2)
              nodeTypes={nodeTypes}
              nodesDraggable={false}
              nodesConnectable={false}
              // TODO: enable connections when edge topology is introduced (Phase 2)
              elementsSelectable={false}
              // ReactFlow sets pointer-events: none inline on every node unless it's
              // selectable, draggable, or has an onNode* handler — all of which we've
              // disabled above. This no-op handler keeps nodes interactive for hover/click.
              onNodeMouseEnter={() => undefined}
              panOnDrag
              zoomOnScroll
              zoomOnPinch
              zoomOnDoubleClick
              fitView
              fitViewOptions={{ padding: 0.3 }}
              proOptions={{ hideAttribution: true }}
            >
              <Background gap={24} size={1} />
              <Controls showInteractive={false} />
              {/* TODO: MiniMap removed — nodes weren't rendering inside it, revisit with @xyflow/react's measured-node store */}
            </ReactFlow>

            {filteredAgents.length === 0 && (
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                <p className="text-body text-muted">No agents match &ldquo;{searchQuery}&rdquo;.</p>
              </div>
            )}

            <div className="absolute left-4 top-4 z-10 flex items-center gap-3">
              <div className="pointer-events-none flex items-center gap-3 rounded-lg border border-border bg-surface/60 px-3 py-1.5 backdrop-blur-sm">
                <span className="flex items-center gap-1.5 text-label font-medium text-success">
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  Active
                </span>
                <span className="w-px self-stretch bg-border" />
                <span className="flex items-center gap-1.5 text-label font-medium text-muted">
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  Inactive
                </span>
              </div>

              <div className="flex items-center gap-2 rounded-lg border border-border bg-surface/60 px-3 py-1.5 backdrop-blur-sm">
                <IconSearch size={14} className="text-muted" />
                <input
                  type="text"
                  placeholder="Search agents…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-32 bg-transparent text-label text-foreground placeholder:text-muted focus:outline-none"
                />
              </div>
            </div>

            <div className="absolute bottom-6 right-6 z-10">
              <SpawnAgentButton onClick={() => setSpawnOpen(true)} />
            </div>
          </>
        )}
      </div>

      <SpawnAgentDialog
        workspaceId={workspaceId}
        open={spawnOpen}
        onOpenChange={setSpawnOpen}
      />
    </div>
  )
}
