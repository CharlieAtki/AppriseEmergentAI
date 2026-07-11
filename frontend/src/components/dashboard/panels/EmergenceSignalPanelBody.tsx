'use client'

import { useMemo } from 'react'
import { Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useGetWorkspaceEmergenceWorkspacesWorkspaceIdEmergenceGet } from '@/api/generated/workspaces/workspaces'
import { mockEmergenceEvents } from '@/lib/devMockData'
import { useTimeWindow } from '@/hooks/dashboard/useTimeWindow'
import { useDashboardDevModeStore } from '@/stores/dashboardDevMode'
import type { DashboardPanelInstance } from '@/stores/dashboardLayout'
import { PanelEmptyState } from './PanelEmptyState'

export interface EmergenceSignalConfig {
  timeRange?: '24h' | '7d' | '30d' | '90d'
  showHubMarkers?: boolean
}

const RANGE_HOURS: Record<NonNullable<EmergenceSignalConfig['timeRange']>, number> = {
  '24h': 24,
  '7d': 24 * 7,
  '30d': 24 * 30,
  '90d': 24 * 90,
}

interface EmergenceSignalPanelBodyProps {
  workspaceId: string
  panel: DashboardPanelInstance
}

export function EmergenceSignalPanelBody({ workspaceId, panel }: EmergenceSignalPanelBodyProps) {
  const config = panel.config as EmergenceSignalConfig
  const timeRange = config.timeRange ?? '24h'
  const showHubMarkers = config.showHubMarkers ?? true

  const devMode = useDashboardDevModeStore((s) => s.enabled)
  const timeWindow = useTimeWindow(RANGE_HOURS[timeRange])

  const { data: fetchedEvents } = useGetWorkspaceEmergenceWorkspacesWorkspaceIdEmergenceGet(
    workspaceId,
    { since: timeWindow?.since, limit: 200 },
    { query: { enabled: timeWindow !== undefined && !devMode } },
  )
  const events =
    devMode && timeWindow
      ? mockEmergenceEvents(timeWindow.nowMs - RANGE_HOURS[timeRange] * 60 * 60 * 1000, timeWindow.nowMs)
      : fetchedEvents

  const series = useMemo(
    () =>
      [...(events ?? [])]
        .filter((e) => e.gini_coefficient != null)
        .sort((a, b) => new Date(a.recorded_at).getTime() - new Date(b.recorded_at).getTime()),
    [events],
  )
  const hubEvents = useMemo(
    () => (showHubMarkers ? series.filter((e) => e.event_type === 'hub_detected') : []),
    [series, showHubMarkers],
  )

  if (series.length < 2) {
    return <PanelEmptyState message="Not enough activity yet to chart the emergence signal." />
  }

  return (
    <div className="h-full p-3">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={series} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
          <XAxis dataKey="recorded_at" hide />
          <YAxis domain={[0, 1]} width={32} tick={{ fill: 'var(--color-muted)', fontSize: 11 }} />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--color-elevated)',
              border: '1px solid var(--color-border)',
              borderRadius: 8,
            }}
            labelFormatter={(label) => new Date(label as string).toLocaleString()}
          />
          <Line
            type="monotone"
            dataKey="gini_coefficient"
            stroke="var(--color-text-primary)"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
          {hubEvents.map((event) => (
            <ReferenceDot
              key={event.id}
              x={event.recorded_at}
              y={event.gini_coefficient ?? 0}
              r={4}
              fill="var(--color-highlight)"
              stroke="var(--color-highlight)"
              strokeOpacity={0.35}
              strokeWidth={4}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
