"use client";

import { Button } from "@/components/ui/button";
import { motion, useReducedMotion } from "framer-motion";
import { forwardRef, useMemo } from "react";
import { Line, LineChart, XAxis, YAxis } from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { getChartColor } from "@/lib/chartColors";
import { panelExpandSpring } from "@/lib/motion";
import { IconClose } from "@/lib/icons";
import type {
  AgentResponse,
  InfluenceHistoryPointResponse,
} from "@/api/generated/model";
import { PanelEmptyState } from "./PanelEmptyState";
interface Props {
  panelId: string;
  agent: AgentResponse;
  series: InfluenceHistoryPointResponse[];
  onClose: () => void;
}
export const AgentPoolExpandedChart = forwardRef<HTMLButtonElement, Props>(
  function AgentPoolExpandedChart(
    { panelId, agent, series, onClose },
    closeButtonRef,
  ) {
    const shouldReduceMotion = useReducedMotion();
    const latest = series.at(-1)?.influence;
    const chartConfig = useMemo(
      () =>
        ({
          influence: { label: "Influence", color: getChartColor(agent.id) },
        }) satisfies ChartConfig,
      [agent.id],
    );
    return (
      <motion.div
        layoutId={`agent-pool-${panelId}-${agent.id}`}
        transition={shouldReduceMotion ? { duration: 0 } : panelExpandSpring}
        className="flex h-full flex-col gap-2 p-3"
      >
        <div className="flex shrink-0 items-center justify-between gap-2">
          <div className="flex items-baseline gap-2">
            <span className="text-label font-semibold text-foreground">
              {agent.name}
            </span>
            {latest != null && (
              <span className="text-caption text-muted">
                {latest.toFixed(2)}
              </span>
            )}
          </div>
          <Button
            ref={closeButtonRef}
            onClick={onClose}
            aria-label="Close expanded chart"
            variant="ghost"
            size="icon"
            className="rounded p-1 text-muted transition-colors hover:bg-hover hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-primary"
          >
            <IconClose size={14} />
          </Button>
        </div>
        {series.length < 2 ? (
          <div className="flex-1">
            <PanelEmptyState message="Not enough activity yet" />
          </div>
        ) : (
          <ChartContainer
            config={chartConfig}
            className="min-h-0 flex-1 w-full aspect-auto"
          >
            <LineChart
              data={series}
              margin={{ top: 4, right: 8, bottom: 0, left: -20 }}
            >
              <XAxis dataKey="recorded_at" />
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
                dataKey="influence"
                name="Influence"
                stroke="var(--color-influence)"
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ChartContainer>
        )}
      </motion.div>
    );
  },
);
