'use client'

import { useListAgentsWorkspacesWorkspaceIdAgentsGet } from '@/api/generated/agents/agents'
import type { AgentLanesConfig } from '../AgentLanesPanelBody'

interface AgentLanesConfigFormProps {
  workspaceId: string
  config: AgentLanesConfig
  onChange: (config: AgentLanesConfig) => void
}

export function AgentLanesConfigForm({ workspaceId, config, onChange }: AgentLanesConfigFormProps) {
  const { data: agents } = useListAgentsWorkspacesWorkspaceIdAgentsGet(workspaceId)

  function toggleAgent(id: string) {
    const current = config.agentIds ?? []
    const next = current.includes(id) ? current.filter((a) => a !== id) : [...current, id]
    onChange({ ...config, agentIds: next })
  }

  return (
    <div className="flex flex-col gap-3">
      <div>
        <label className="text-caption font-semibold uppercase tracking-architectural text-muted">Time window</label>
        <select
          value={config.window ?? '6h'}
          onChange={(e) => onChange({ ...config, window: e.target.value as '1h' | '6h' | '24h' })}
          className="mt-1 w-full rounded-md border border-border bg-elevated px-2 py-1.5 text-body text-foreground"
        >
          <option value="1h">1 hour</option>
          <option value="6h">6 hours</option>
          <option value="24h">24 hours</option>
        </select>
      </div>

      <div>
        <label className="text-caption font-semibold uppercase tracking-architectural text-muted">Group by</label>
        <select
          value={config.groupBy ?? 'status'}
          onChange={(e) => onChange({ ...config, groupBy: e.target.value as 'task' | 'status' })}
          className="mt-1 w-full rounded-md border border-border bg-elevated px-2 py-1.5 text-body text-foreground"
        >
          <option value="status">Status</option>
          <option value="task">Task</option>
        </select>
      </div>

      <div>
        <label className="text-caption font-semibold uppercase tracking-architectural text-muted">Agents</label>
        <p className="mt-0.5 text-caption text-muted">Leave empty to show all agents as lanes.</p>
        <div className="mt-1.5 max-h-32 space-y-1 overflow-y-auto">
          {(agents ?? []).map((agent) => (
            <label key={agent.id} className="flex items-center gap-2 text-caption text-secondary">
              <input
                type="checkbox"
                checked={(config.agentIds ?? []).includes(agent.id)}
                onChange={() => toggleAgent(agent.id)}
              />
              {agent.name}
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}
