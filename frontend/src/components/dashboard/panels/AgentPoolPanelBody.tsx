"use client";

import { Button } from "@/components/ui/button";

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Line, LineChart, ResponsiveContainer } from "recharts";
import { useListAgentsWorkspacesWorkspaceIdAgentsGet } from "@/api/generated/agents/agents";
import { useGetAgentsInfluenceHistoryWorkspacesWorkspaceIdAgentsInfluenceHistoryGet } from "@/api/generated/agents/agents";
import { getChartColor } from "@/lib/chartColors";
import { mockInfluenceHistory } from "@/lib/devMockData";
import { useTimeWindow } from "@/hooks/dashboard/useTimeWindow";
import { usePagedIndex } from "@/hooks/dashboard/usePagedIndex";
import { useDashboardDevModeStore } from "@/stores/dashboardDevMode";
import { IconExpand } from "@/lib/icons";
import type { DashboardPanelInstance } from "@/stores/dashboardLayout";
import { PanelEmptyState } from "./PanelEmptyState";
import { AgentPoolExpandedChart } from "./AgentPoolExpandedChart";
import { DashboardPagerArrow } from "../DashboardPagerArrow";
import { DashboardPagerDots } from "../DashboardPagerDots";

export interface AgentPoolConfig {
  agentIds?: string[];
  sort?: "influence" | "name";
  windowMode?: "calendar" | "last-n";
  calendarRange?: "24h" | "7d" | "30d";
  lastN?: number;
}

const CALENDAR_HOURS: Record<
  NonNullable<AgentPoolConfig["calendarRange"]>,
  number
> = {
  "24h": 24,
  "7d": 24 * 7,
  "30d": 24 * 30,
};

// Sparklines shown scales with panel footprint — "show 4 on the smaller
// panel, more on the larger grid" per the original spec. Clamped to a
// sensible floor/ceiling so a 1-cell panel doesn't try to render nothing
// and a huge panel doesn't try to render fifty tiny charts. Now doubles as
// the page size for pagination, rather than a hard cap that silently drops
// agents beyond it.
function sparklineCount(w: number, h: number): number {
  return Math.max(2, Math.min(12, Math.floor((w * h) / 4)));
}

function SparklineCardSkeleton() {
  return (
    <div
      className="flex flex-col gap-1 rounded-md bg-elevated p-2"
      aria-hidden="true"
    >
      <div className="h-3 w-16 rounded bg-hover motion-safe:animate-pulse" />
      <div className="mt-1 h-6 flex-1 rounded bg-hover motion-safe:animate-pulse" />
    </div>
  );
}

interface AgentPoolPanelBodyProps {
  workspaceId: string;
  panel: DashboardPanelInstance;
}

export function AgentPoolPanelBody({
  workspaceId,
  panel,
}: AgentPoolPanelBodyProps) {
  const config = panel.config as AgentPoolConfig;
  const sort = config.sort ?? "influence";
  const windowMode = config.windowMode ?? "calendar";
  const calendarRange = config.calendarRange ?? "24h";
  const lastN = config.lastN ?? 5;

  const { data: agents } =
    useListAgentsWorkspacesWorkspaceIdAgentsGet(workspaceId);

  const allSelectedAgents = useMemo(() => {
    const pool = agents ?? [];
    const filtered = config.agentIds?.length
      ? pool.filter((a) => config.agentIds!.includes(a.id))
      : pool;
    return [...filtered].sort((a, b) =>
      sort === "name"
        ? a.name.localeCompare(b.name)
        : (b.influence ?? 0) - (a.influence ?? 0),
    );
  }, [agents, config.agentIds, sort]);

  const pageSize = sparklineCount(panel.w, panel.h);
  const { page, pageCount, setPage, goPrev, goNext, canGoPrev, canGoNext } =
    usePagedIndex({
      itemCount: allSelectedAgents.length,
      pageSize,
    });

  const selectedAgents = useMemo(
    () => allSelectedAgents.slice(page * pageSize, page * pageSize + pageSize),
    [allSelectedAgents, page, pageSize],
  );

  const agentIds = useMemo(
    () => selectedAgents.map((a) => a.id),
    [selectedAgents],
  );
  const devMode = useDashboardDevModeStore((s) => s.enabled);

  const timeWindow = useTimeWindow(CALENDAR_HOURS[calendarRange]);
  const since = windowMode === "calendar" ? timeWindow?.since : undefined;
  const ready = windowMode === "last-n" || timeWindow !== undefined;

  const { data: fetchedPoints } =
    useGetAgentsInfluenceHistoryWorkspacesWorkspaceIdAgentsInfluenceHistoryGet(
      workspaceId,
      {
        agent_id: agentIds,
        since,
        limit: windowMode === "last-n" ? lastN : undefined,
      },
      { query: { enabled: agentIds.length > 0 && ready && !devMode } },
    );
  const points =
    devMode && timeWindow
      ? mockInfluenceHistory(
          agentIds,
          timeWindow.nowMs - CALENDAR_HOURS[calendarRange] * 60 * 60 * 1000,
          timeWindow.nowMs,
        )
      : fetchedPoints;

  const [expandedAgentId, setExpandedAgentId] = useState<string | null>(null);
  const shouldReduceMotion = useReducedMotion();
  const triggerRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!expandedAgentId) return;
    closeButtonRef.current?.focus();
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") collapse();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expandedAgentId]);

  function collapse() {
    const returnFocusTo = expandedAgentId
      ? triggerRefs.current[expandedAgentId]
      : null;
    setExpandedAgentId(null);
    // Trigger button may have scrolled out of the current page — fall back
    // to the panel body itself so focus doesn't silently drop to <body>.
    (returnFocusTo ?? containerRef.current)?.focus();
  }

  if (agents === undefined) {
    return (
      <div
        className="grid h-full gap-2 p-3"
        style={{
          gridTemplateColumns: `repeat(${Math.min(sparklineCount(panel.w, panel.h), 4)}, minmax(0, 1fr))`,
        }}
      >
        {Array.from(
          { length: Math.min(sparklineCount(panel.w, panel.h), 4) },
          (_, i) => (
            <SparklineCardSkeleton key={i} />
          ),
        )}
      </div>
    );
  }
  if (allSelectedAgents.length === 0) {
    return <PanelEmptyState message="No agents in this workspace yet." />;
  }
  if (points === undefined) {
    return (
      <div
        className="grid h-full gap-2 p-3"
        style={{
          gridTemplateColumns: `repeat(${Math.min(selectedAgents.length, 4)}, minmax(0, 1fr))`,
        }}
      >
        {selectedAgents.map((agent) => (
          <SparklineCardSkeleton key={agent.id} />
        ))}
      </div>
    );
  }

  const expandedAgent = expandedAgentId
    ? (allSelectedAgents.find((a) => a.id === expandedAgentId) ?? null)
    : null;

  return (
    <div
      ref={containerRef}
      tabIndex={-1}
      className="flex h-full flex-col outline-none"
    >
      <div className="min-h-0 flex-1">
        <AnimatePresence mode="wait">
          {expandedAgent ? (
            <AgentPoolExpandedChart
              key="expanded"
              ref={closeButtonRef}
              panelId={panel.i}
              agent={expandedAgent}
              series={points.filter((p) => p.agent_id === expandedAgent.id)}
              onClose={collapse}
            />
          ) : (
            <div
              key="grid"
              className="grid h-full gap-2 p-3"
              style={{
                gridTemplateColumns: `repeat(${Math.min(selectedAgents.length, 4)}, minmax(0, 1fr))`,
              }}
            >
              {selectedAgents.map((agent) => {
                const series = points.filter((p) => p.agent_id === agent.id);
                return (
                  <div
                    key={agent.id}
                    className="group/card relative flex flex-col gap-1 rounded-md bg-elevated p-2"
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="truncate text-caption text-secondary">
                        {agent.name}
                      </span>
                      <Button
                        ref={(el) => {
                          triggerRefs.current[agent.id] = el;
                        }}
                        onClick={() => setExpandedAgentId(agent.id)}
                        aria-label={`Expand ${agent.name}'s chart`}
                        className="shrink-0 rounded p-0.5 text-muted opacity-0 transition-opacity hover:bg-hover hover:text-foreground group-hover/card:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-primary"
                      >
                        <IconExpand size={11} />
                      </Button>
                    </div>
                    <motion.div
                      layoutId={`agent-pool-${panel.i}-${agent.id}`}
                      transition={
                        shouldReduceMotion
                          ? { duration: 0 }
                          : { type: "spring", damping: 30, stiffness: 300 }
                      }
                      className="flex-1"
                    >
                      {series.length < 2 ? (
                        <PanelEmptyState message="Not enough activity yet" />
                      ) : (
                        <ResponsiveContainer
                          width="100%"
                          height="100%"
                          minHeight={32}
                        >
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
                    </motion.div>
                  </div>
                );
              })}
            </div>
          )}
        </AnimatePresence>
      </div>

      {pageCount > 1 && !expandedAgent && (
        <div className="flex h-11 shrink-0 items-center justify-center gap-1 border-t border-border">
          <DashboardPagerArrow
            direction="prev"
            disabled={!canGoPrev}
            onClick={goPrev}
          />
          <DashboardPagerDots
            page={page}
            pageCount={pageCount}
            onChange={setPage}
          />
          <DashboardPagerArrow
            direction="next"
            disabled={!canGoNext}
            onClick={goNext}
          />
        </div>
      )}
    </div>
  );
}
