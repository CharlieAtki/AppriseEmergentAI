'use client'

import { useMemo } from 'react'
import { Line, LineChart, ResponsiveContainer } from 'recharts'
import { useListAgentsWorkspacesWorkspaceIdAgentsGet } from '@/api/generated/agents/agents'
import { useGetAgentsInfluenceHistoryWorkspacesWorkspaceIdAgentsInfluenceHistoryGet } from '@/api/generated/agents/agents'
import { getChartColor } from '@/lib/chartColors'
import { mockInfluenceHistory } from '@/lib/devMockData'
import { useTimeWindow } from '@/hooks/dashboard/useTimeWindow'
import { useDashboardDevModeStore } from '@/stores/dashboardDevMode'
import type { DashboardPanelInstance } from '@/stores/dashboardLayout'
import { PanelEmptyState } from './PanelEmptyState'

export interface AgentPoolConfig {
  agentIds?: string[]
  sort?: 'influence' | 'name'
  windowMode?: 'calendar' | 'last-n'
  calendarRange?: '24h' | '7d' | '30d'
  lastN?: number
}

const CALENDAR_HOURS: Record<NonNullable<AgentPoolConfig['calendarRange']>, number> = {
  '24h': 24,
  '7d': 24 * 7,
  '30d': 24 * 30,
}

// Sparklines shown scales with panel footprint — "show 4 on the smaller
// panel, more on the larger grid" per the original spec. Clamped to a
// sensible floor/ceiling so a 1-cell panel doesn't try to render nothing
// and a huge panel doesn't try to render fifty tiny charts.
function sparklineCount(w: number, h: number): number {
  return Math.max(2, Math.min(12, Math.floor((w * h) / 4)))
}

interface AgentPoolPanelBodyProps {
  workspaceId: string
  panel: DashboardPanelInstance
}

export function AgentPoolPanelBody({ workspaceId, panel }: AgentPoolPanelBodyProps) {
  const config = panel.config as AgentPoolConfig
  const sort = config.sort ?? 'influence'
  const windowMode = config.windowMode ?? 'calendar'
  const calendarRange = config.calendarRange ?? '24h'
  const lastN = config.lastN ?? 5

  const { data: agents } = useListAgentsWorkspacesWorkspaceIdAgentsGet(workspaceId)

  const selectedAgents = useMemo(() => {
    const pool = agents ?? []
    const filtered = config.agentIds?.length
      ? pool.filter((a) => config.agentIds!.includes(a.id))
      : pool
    const sorted = [...filtered].sort((a, b) =>
      sort === 'name' ? a.name.localeCompare(b.name) : (b.influence ?? 0) - (a.influence ?? 0),
    )
    return sorted.slice(0, sparklineCount(panel.w, panel.h))
  }, [agents, config.agentIds, sort, panel.w, panel.h])

  const agentIds = useMemo(() => selectedAgents.map((a) => a.id), [selectedAgents])
  const devMode = useDashboardDevModeStore((s) => s.enabled)

  const timeWindow = useTimeWindow(CALENDAR_HOURS[calendarRange])
  const since = windowMode === 'calendar' ? timeWindow?.since : undefined
  const ready = windowMode === 'last-n' || timeWindow !== undefined

  const { data: fetchedPoints } = useGetAgentsInfluenceHistoryWorkspacesWorkspaceIdAgentsInfluenceHistoryGet(
    workspaceId,
    { agent_id: agentIds, since, limit: windowMode === 'last-n' ? lastN : undefined },
    { query: { enabled: agentIds.length > 0 && ready && !devMode } },
  )
  const points =
    devMode && timeWindow
      ? mockInfluenceHistory(agentIds, timeWindow.nowMs - CALENDAR_HOURS[calendarRange] * 60 * 60 * 1000, timeWindow.nowMs)
      : fetchedPoints

  if (selectedAgents.length === 0) {
    return <PanelEmptyState message="No agents in this workspace yet." />
  }

  return (
    <div
      className="grid h-full gap-2 p-3"
      style={{ gridTemplateColumns: `repeat(${Math.min(selectedAgents.length, 4)}, minmax(0, 1fr))` }}
    >
      {selectedAgents.map((agent) => {
        const series = (points ?? []).filter((p) => p.agent_id === agent.id)
        return (
          <div key={agent.id} className="flex flex-col gap-1 rounded-md bg-elevated p-2">
            <span className="truncate text-caption text-secondary">{agent.name}</span>
            {series.length < 2 ? (
              <div className="flex-1">
                <PanelEmptyState message="Not enough activity yet" />
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%" minHeight={32}>
                <LineChart data={series}>
                  <Line
                    type="monotone"
                    dataKey="influence"
                    stroke={getChartColor(agent.id)}
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        )
      })}
    </div>
  )
}
