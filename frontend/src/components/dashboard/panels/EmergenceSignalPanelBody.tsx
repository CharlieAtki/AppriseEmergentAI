"use client";

import { Line, LineChart, ReferenceDot, XAxis, YAxis } from "recharts";
import { useMemo } from "react";
import { useGetWorkspaceEmergenceWorkspacesWorkspaceIdEmergenceGet } from "@/api/generated/workspaces/workspaces";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { mockEmergenceEvents } from "@/lib/devMockData";
import { useTimeWindow } from "@/hooks/dashboard/useTimeWindow";
import { useDashboardDevModeStore } from "@/stores/dashboardDevMode";
import type { DashboardPanelInstance } from "@/stores/dashboardLayout";
import { PanelEmptyState } from "./PanelEmptyState";

export interface EmergenceSignalConfig {
  timeRange?: "24h" | "7d" | "30d" | "90d";
  showHubMarkers?: boolean;
}
const RANGE_HOURS: Record<
  NonNullable<EmergenceSignalConfig["timeRange"]>,
  number
> = { "24h": 24, "7d": 168, "30d": 720, "90d": 2160 };
const chartConfig = {
  gini_coefficient: {
    label: "Gini coefficient",
    color: "var(--color-text-primary)",
  },
} satisfies ChartConfig;
interface Props {
  workspaceId: string;
  panel: DashboardPanelInstance;
}

export function EmergenceSignalPanelBody({ workspaceId, panel }: Props) {
  const config = panel.config as EmergenceSignalConfig;
  const timeRange = config.timeRange ?? "24h";
  const devMode = useDashboardDevModeStore((state) => state.enabled);
  const timeWindow = useTimeWindow(RANGE_HOURS[timeRange]);
  const { data: fetchedEvents } =
    useGetWorkspaceEmergenceWorkspacesWorkspaceIdEmergenceGet(
      workspaceId,
      { since: timeWindow?.since, limit: 200 },
      { query: { enabled: timeWindow !== undefined && !devMode } },
    );
  const events =
    devMode && timeWindow
      ? mockEmergenceEvents(
          timeWindow.nowMs - RANGE_HOURS[timeRange] * 3_600_000,
          timeWindow.nowMs,
        )
      : fetchedEvents;
  const series = useMemo(
    () =>
      [...(events ?? [])]
        .filter((event) => event.gini_coefficient != null)
        .sort(
          (a, b) =>
            new Date(a.recorded_at).getTime() -
            new Date(b.recorded_at).getTime(),
        ),
    [events],
  );
  const hubEvents = useMemo(
    () =>
      (config.showHubMarkers ?? true)
        ? series.filter((event) => event.event_type === "hub_detected")
        : [],
    [config.showHubMarkers, series],
  );
  if (series.length < 2)
    return (
      <PanelEmptyState message="Not enough activity yet to chart the emergence signal." />
    );
  return (
    <div className="h-full p-3">
      <ChartContainer
        config={chartConfig}
        className="h-full w-full aspect-auto"
      >
        <LineChart
          data={series}
          margin={{ top: 4, right: 8, bottom: 0, left: -20 }}
        >
          <XAxis dataKey="recorded_at" hide />
          <YAxis domain={[0, 1]} width={32} />
          <ChartTooltip
            content={
              <ChartTooltipContent
                indicator="line"
                labelFormatter={(label) =>
                  new Date(String(label)).toLocaleString()
                }
              />
            }
          />
          <Line
            type="monotone"
            dataKey="gini_coefficient"
            name="Gini coefficient"
            stroke="var(--color-gini_coefficient)"
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
      </ChartContainer>
    </div>
  );
}
