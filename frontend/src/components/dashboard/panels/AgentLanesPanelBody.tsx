'use client'

import { useMemo } from 'react'
import { useListAgentsWorkspacesWorkspaceIdAgentsGet } from '@/api/generated/agents/agents'
import { useGetAgentsTaskTimelineWorkspacesWorkspaceIdAgentsTaskTimelineGet } from '@/api/generated/agents/agents'
import { getChartColor, getStatusChartColor } from '@/lib/chartColors'
import { mockTaskTimeline } from '@/lib/devMockData'
import { useTimeWindow } from '@/hooks/dashboard/useTimeWindow'
import { useDashboardDevModeStore } from '@/stores/dashboardDevMode'
import type { TaskTimelineEntryResponse } from '@/api/generated/model'
import type { DashboardPanelInstance } from '@/stores/dashboardLayout'
import { PanelEmptyState } from './PanelEmptyState'

export interface AgentLanesConfig {
  agentIds?: string[]
  window?: '1h' | '6h' | '24h'
  groupBy?: 'task' | 'status'
}

const WINDOW_HOURS: Record<NonNullable<AgentLanesConfig['window']>, number> = {
  '1h': 1,
  '6h': 6,
  '24h': 24,
}

function segmentColor(entry: TaskTimelineEntryResponse, groupBy: NonNullable<AgentLanesConfig['groupBy']>) {
  return groupBy === 'status' ? getStatusChartColor(entry.status) : getChartColor(entry.task_id)
}

interface AgentLanesPanelBodyProps {
  workspaceId: string
  panel: DashboardPanelInstance
}

export function AgentLanesPanelBody({ workspaceId, panel }: AgentLanesPanelBodyProps) {
  const config = panel.config as AgentLanesConfig
  const windowKey = config.window ?? '6h'
  const groupBy = config.groupBy ?? 'status'

  const { data: agents } = useListAgentsWorkspacesWorkspaceIdAgentsGet(workspaceId)

  const selectedAgents = useMemo(() => {
    const pool = agents ?? []
    return config.agentIds?.length ? pool.filter((a) => config.agentIds!.includes(a.id)) : pool
  }, [agents, config.agentIds])
  const agentIds = useMemo(() => selectedAgents.map((a) => a.id), [selectedAgents])
  const devMode = useDashboardDevModeStore((s) => s.enabled)

  const timeWindow = useTimeWindow(WINDOW_HOURS[windowKey])

  const { data: fetchedExecutions } = useGetAgentsTaskTimelineWorkspacesWorkspaceIdAgentsTaskTimelineGet(
    workspaceId,
    { agent_id: agentIds, since: timeWindow?.since },
    { query: { enabled: agentIds.length > 0 && timeWindow !== undefined && !devMode } },
  )
  const executions =
    devMode && timeWindow
      ? mockTaskTimeline(agentIds, timeWindow.nowMs - WINDOW_HOURS[windowKey] * 60 * 60 * 1000, timeWindow.nowMs)
      : fetchedExecutions

  if (selectedAgents.length === 0) {
    return <PanelEmptyState message="No agents in this workspace yet." />
  }
  if (!timeWindow || !executions || executions.length === 0) {
    return <PanelEmptyState message="No task activity in this window." />
  }

  const windowEnd = timeWindow.nowMs
  const windowStart = windowEnd - WINDOW_HOURS[windowKey] * 60 * 60 * 1000
  const windowMs = windowEnd - windowStart

  return (
    <div className="flex h-full flex-col gap-2 overflow-y-auto p-3">
      {selectedAgents.map((agent) => {
        const entries = executions.filter((e) => e.agent_id === agent.id && e.started_at)
        return (
          <div key={agent.id} className="flex items-center gap-2">
            <span className="w-20 shrink-0 truncate text-caption text-secondary">{agent.name}</span>
            <div className="relative h-4 flex-1 rounded bg-elevated">
              {entries.map((entry) => {
                const start = new Date(entry.started_at!).getTime()
                const end = entry.completed_at ? new Date(entry.completed_at).getTime() : windowEnd
                const left = Math.max(0, ((start - windowStart) / windowMs) * 100)
                const width = Math.max(1, ((end - start) / windowMs) * 100)
                return (
                  <div
                    key={entry.id}
                    className="absolute top-0 h-full rounded-sm"
                    style={{
                      left: `${left}%`,
                      width: `${width}%`,
                      backgroundColor: segmentColor(entry, groupBy),
                    }}
                    title={`${entry.status} · ${entry.started_at}`}
                  />
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
