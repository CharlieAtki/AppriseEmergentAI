'use client'

import { useListAgentsWorkspacesWorkspaceIdAgentsGet } from '@/api/generated/agents/agents'
import type { AgentPoolConfig } from '../AgentPoolPanelBody'

interface AgentPoolConfigFormProps {
  workspaceId: string
  config: AgentPoolConfig
  onChange: (config: AgentPoolConfig) => void
}

export function AgentPoolConfigForm({ workspaceId, config, onChange }: AgentPoolConfigFormProps) {
  const { data: agents } = useListAgentsWorkspacesWorkspaceIdAgentsGet(workspaceId)
  const windowMode = config.windowMode ?? 'calendar'

  function toggleAgent(id: string) {
    const current = config.agentIds ?? []
    const next = current.includes(id) ? current.filter((a) => a !== id) : [...current, id]
    onChange({ ...config, agentIds: next })
  }

  return (
    <div className="flex flex-col gap-3">
      <div>
        <label className="text-caption font-semibold uppercase tracking-architectural text-muted">Sort</label>
        <select
          value={config.sort ?? 'influence'}
          onChange={(e) => onChange({ ...config, sort: e.target.value as 'influence' | 'name' })}
          className="mt-1 w-full rounded-md border border-border bg-elevated px-2 py-1.5 text-body text-foreground"
        >
          <option value="influence">Influence</option>
          <option value="name">Name</option>
        </select>
      </div>

      <div>
        <label className="text-caption font-semibold uppercase tracking-architectural text-muted">Trend window</label>
        <div className="mt-1 flex gap-1">
          <button
            onClick={() => onChange({ ...config, windowMode: 'calendar' })}
            className={`flex-1 rounded-md px-2 py-1 text-caption ${windowMode === 'calendar' ? 'bg-brand-primary text-background' : 'bg-elevated text-muted'}`}
          >
            Calendar
          </button>
          <button
            onClick={() => onChange({ ...config, windowMode: 'last-n' })}
            className={`flex-1 rounded-md px-2 py-1 text-caption ${windowMode === 'last-n' ? 'bg-brand-primary text-background' : 'bg-elevated text-muted'}`}
          >
            Last N points
          </button>
        </div>
        {windowMode === 'calendar' ? (
          <select
            value={config.calendarRange ?? '24h'}
            onChange={(e) => onChange({ ...config, calendarRange: e.target.value as '24h' | '7d' | '30d' })}
            className="mt-1.5 w-full rounded-md border border-border bg-elevated px-2 py-1.5 text-body text-foreground"
          >
            <option value="24h">24 hours</option>
            <option value="7d">7 days</option>
            <option value="30d">30 days</option>
          </select>
        ) : (
          <input
            type="number"
            min={1}
            max={50}
            value={config.lastN ?? 5}
            onChange={(e) => onChange({ ...config, lastN: Number(e.target.value) })}
            className="mt-1.5 w-full rounded-md border border-border bg-elevated px-2 py-1.5 text-body text-foreground"
          />
        )}
      </div>

      <div>
        <label className="text-caption font-semibold uppercase tracking-architectural text-muted">Agents</label>
        <p className="mt-0.5 text-caption text-muted">Leave empty to show all, sorted and sized to fit.</p>
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
