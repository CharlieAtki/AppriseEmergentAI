"use client";

import { useMemo } from "react";
import { Tooltip, TooltipProvider, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { useListAgentsWorkspacesWorkspaceIdAgentsGet } from "@/api/generated/agents/agents";
import { useGetAgentsTaskTimelineWorkspacesWorkspaceIdAgentsTaskTimelineGet } from "@/api/generated/agents/agents";
import {
  getStatusChartColor,
  getTaskChartColor,
  STATUS_CHART_LEGEND,
} from "@/lib/chartColors";
import { mockTaskTimeline } from "@/lib/devMockData";
import { useTimeWindow } from "@/hooks/dashboard/useTimeWindow";
import { useDashboardDevModeStore } from "@/stores/dashboardDevMode";
import { AgentAvatar } from "@/components/agents/AgentAvatar";
import type { TaskTimelineEntryResponse } from "@/api/generated/model";
import type { DashboardPanelInstance } from "@/stores/dashboardLayout";
import { PanelEmptyState } from "./PanelEmptyState";
import { ChartTooltipCard } from "./ChartTooltipCard";

export interface AgentLanesConfig {
  agentIds?: string[];
  window?: "1h" | "6h" | "24h";
  groupBy?: "task" | "status";
}

const WINDOW_HOURS: Record<NonNullable<AgentLanesConfig["window"]>, number> = {
  "1h": 1,
  "6h": 6,
  "24h": 24,
};

// Segments narrower than this read as a sliver rather than a pill — floor the
// rendered width so even a short task stays a visible, tappable mark.
const MIN_SEGMENT_WIDTH_PERCENT = 1.5;

function segmentColor(
  entry: TaskTimelineEntryResponse,
  groupBy: NonNullable<AgentLanesConfig["groupBy"]>,
) {
  return groupBy === "status"
    ? getStatusChartColor(entry.status)
    : getTaskChartColor(entry.task_id);
}

function segmentLabel(
  entry: TaskTimelineEntryResponse,
  groupBy: NonNullable<AgentLanesConfig["groupBy"]>,
) {
  const time = entry.started_at
    ? new Date(entry.started_at).toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit",
      })
    : "unknown time";
  // Color alone never carries the signal — status/task identity is spelled
  // out here so it reaches screen readers, not just a mouse-hover title.
  return groupBy === "status"
    ? `${entry.status} · started ${time}`
    : `Task ${entry.task_id.slice(0, 8)} · started ${time}`;
}

function LaneRowSkeleton() {
  return (
    <div className="flex items-center gap-2 py-1" aria-hidden="true">
      <div className="flex w-28 shrink-0 items-center gap-1.5">
        <Skeleton className="h-6 w-6 shrink-0 rounded-md bg-elevated motion-reduce:animate-none" />
        <Skeleton className="h-3 w-16 bg-elevated motion-reduce:animate-none" />
      </div>
      <Skeleton className="h-4 flex-1 bg-elevated motion-reduce:animate-none" />
    </div>
  );
}

interface AgentLanesPanelBodyProps {
  workspaceId: string;
  panel: DashboardPanelInstance;
}

export function AgentLanesPanelBody({
  workspaceId,
  panel,
}: AgentLanesPanelBodyProps) {
  const config = panel.config as AgentLanesConfig;
  const windowKey = config.window ?? "24h";
  const groupBy = config.groupBy ?? "status";

  const { data: agents } =
    useListAgentsWorkspacesWorkspaceIdAgentsGet(workspaceId);

  const selectedAgents = useMemo(() => {
    const pool = agents ?? [];
    return config.agentIds?.length
      ? pool.filter((a) => config.agentIds!.includes(a.id))
      : pool;
  }, [agents, config.agentIds]);
  const agentIds = useMemo(
    () => selectedAgents.map((a) => a.id),
    [selectedAgents],
  );
  const devMode = useDashboardDevModeStore((s) => s.enabled);

  const timeWindow = useTimeWindow(WINDOW_HOURS[windowKey]);

  const { data: fetchedExecutions } =
    useGetAgentsTaskTimelineWorkspacesWorkspaceIdAgentsTaskTimelineGet(
      workspaceId,
      { agent_id: agentIds, since: timeWindow?.since },
      {
        query: {
          enabled: agentIds.length > 0 && timeWindow !== undefined && !devMode,
        },
      },
    );
  const executions =
    devMode && timeWindow
      ? mockTaskTimeline(
          agentIds,
          timeWindow.nowMs - WINDOW_HOURS[windowKey] * 60 * 60 * 1000,
          timeWindow.nowMs,
        )
      : fetchedExecutions;

  if (agents === undefined) {
    return (
      <div className="flex h-full flex-col gap-1 overflow-y-auto p-3">
        {Array.from({ length: 3 }, (_, i) => (
          <LaneRowSkeleton key={i} />
        ))}
      </div>
    );
  }
  if (selectedAgents.length === 0) {
    return <PanelEmptyState message="No agents in this workspace yet." />;
  }
  if (timeWindow === undefined || executions === undefined) {
    return (
      <div className="flex h-full flex-col gap-1 overflow-y-auto p-3">
        {selectedAgents.map((agent) => (
          <LaneRowSkeleton key={agent.id} />
        ))}
      </div>
    );
  }

  const windowEnd = timeWindow.nowMs;
  const windowStart = windowEnd - WINDOW_HOURS[windowKey] * 60 * 60 * 1000;
  const windowMs = windowEnd - windowStart;

  return (
    <TooltipProvider delay={120}>
      <div className="flex h-full flex-col gap-1 overflow-y-auto p-3">
        {groupBy === "status" && (
          <div className="mb-1 flex flex-wrap items-center gap-3 border-b border-border pb-2">
            {STATUS_CHART_LEGEND.map(({ status, label }) => (
              <span
                key={status}
                className="flex items-center gap-1.5 text-caption text-muted"
              >
                <span
                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ backgroundColor: getStatusChartColor(status) }}
                />
                {label}
              </span>
            ))}
          </div>
        )}
        {selectedAgents.map((agent) => {
          const entries = executions.filter(
            (e) => e.agent_id === agent.id && e.started_at,
          );
          const idle = entries.length === 0;
          return (
            <div key={agent.id} className="flex items-center gap-2 py-1">
              <div className="flex w-28 shrink-0 items-center gap-1.5">
                <AgentAvatar id={agent.id} name={agent.name} size="sm" />
                <span className="truncate text-caption text-secondary">
                  {agent.name}
                </span>
              </div>
              <div className="relative h-4 flex-1">
                {/* Guide line, not a filled track — segments alone carry the activity signal. */}
                <div className="absolute top-1/2 h-px w-full -translate-y-1/2 bg-border" />
                {idle ? (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 text-caption text-muted">
                    No recent activity
                  </span>
                ) : (
                  entries.map((entry) => {
                    const start = new Date(entry.started_at!).getTime();
                    const end = entry.completed_at
                      ? new Date(entry.completed_at).getTime()
                      : windowEnd;
                    const left = Math.max(
                      0,
                      ((start - windowStart) / windowMs) * 100,
                    );
                    const width = Math.max(
                      MIN_SEGMENT_WIDTH_PERCENT,
                      ((end - start) / windowMs) * 100,
                    );
                    const label = segmentLabel(entry, groupBy);
                    const color = segmentColor(entry, groupBy);
                    return (
                      <Tooltip key={entry.id}>
                        <TooltipTrigger
                          render={
                            <div
                              role="img"
                              aria-label={label}
                              tabIndex={0}
                              className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full outline-none focus-visible:ring-1 focus-visible:ring-brand-primary"
                              style={{
                                left: `${left}%`,
                                width: `${width}%`,
                                backgroundColor: color,
                              }}
                            />
                          }
                        />
                        <TooltipContent side="top" sideOffset={6} className="bg-transparent p-0 shadow-none">
                          <ChartTooltipCard
                            rows={[{ label, value: "", color }]}
                          />
                        </TooltipContent>
                      </Tooltip>
                    );
                  })
                )}
              </div>
            </div>
          );
        })}
      </div>
    </TooltipProvider>
  );
}
