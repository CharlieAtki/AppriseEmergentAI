"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { useListTasksWorkspacesWorkspaceIdTasksGet } from "@/api/generated/tasks/tasks";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/skeleton";
import { panelExpandSpring } from "@/lib/motion";
import { mockTaskFeed } from "@/lib/devMockData";
import { useDashboardDevModeStore } from "@/stores/dashboardDevMode";
import type { DashboardPanelInstance } from "@/lib/personalDashboard";
import { PanelEmptyState } from "./PanelEmptyState";
import { TaskDetailExpanded } from "./TaskDetailExpanded";

interface LiveTaskFeedPanelBodyProps {
  workspaceId: string;
  panel: DashboardPanelInstance;
}

export interface LiveTaskFeedConfig {
  agentIds?: string[];
  statuses?: string[];
  taskTypes?: string[];
  priorities?: string[];
  maxVisible?: number;
}

// Recent-first, bounded — a feed, not a full task archive. useWorkspaceStream
// invalidates this same query on every task.* event, so the list refetches
// live as tasks are created/run/complete/fail.
const FEED_LIMIT = 50;

function TaskRowSkeleton() {
  return (
    <div className="flex flex-col gap-1 px-3 py-2" aria-hidden="true">
      <Skeleton className="h-4 w-20 rounded-full bg-elevated motion-reduce:animate-none" />
      <Skeleton className="h-3 w-2/3 bg-elevated motion-reduce:animate-none" />
    </div>
  );
}

export function LiveTaskFeedPanelBody({ workspaceId, panel }: LiveTaskFeedPanelBodyProps) {
  const devMode = useDashboardDevModeStore((s) => s.enabled);
  const config = panel.config as LiveTaskFeedConfig;

  // Date.now() is impure and must not be called during render (react-hooks/purity)
  // — computed in an effect, same pattern as useTimeWindow. Only needed for the
  // mock feed's relative timestamps; undefined just means "not ready yet".
  const [nowMs, setNowMs] = useState<number | undefined>(undefined);
  useEffect(() => {
    setNowMs(Date.now());
  }, []);

  const { data: fetchedTasks, isError: isTasksError } = useListTasksWorkspacesWorkspaceIdTasksGet(
    workspaceId,
    { limit: FEED_LIMIT },
    { query: { enabled: !devMode } },
  );
  const allTasks = devMode && nowMs !== undefined ? mockTaskFeed(nowMs, FEED_LIMIT) : fetchedTasks;
  const tasks = allTasks
    ?.filter((task) => !config.agentIds?.length || (task.agent_id && config.agentIds.includes(task.agent_id)))
    .filter((task) => !config.statuses?.length || config.statuses.includes(task.status))
    .filter((task) => !config.taskTypes?.length || (task.task_type && config.taskTypes.includes(task.task_type)))
    .filter((task) => !config.priorities?.length || (task.priority && config.priorities.includes(task.priority)))
    .slice(0, config.maxVisible ?? FEED_LIMIT);
  const shouldReduceMotion = useReducedMotion();
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const triggerRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!expandedTaskId) return;
    closeButtonRef.current?.focus();
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") collapse();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expandedTaskId]);

  function collapse() {
    const returnFocusTo = expandedTaskId ? triggerRefs.current[expandedTaskId] : null;
    setExpandedTaskId(null);
    (returnFocusTo ?? containerRef.current)?.focus();
  }

  if (isTasksError) {
    return <PanelEmptyState message="Couldn't load tasks. Try again shortly." />;
  }

  if (tasks === undefined) {
    return (
      <div className="flex h-full flex-col divide-y divide-border-subtle overflow-hidden">
        {Array.from({ length: 6 }, (_, i) => (
          <TaskRowSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (tasks.length === 0) {
    const hasActiveFilters =
      !!config.agentIds?.length || !!config.statuses?.length || !!config.taskTypes?.length || !!config.priorities?.length;
    return (
      <PanelEmptyState
        message={hasActiveFilters ? "No tasks match the current filters." : "No tasks in this workspace yet."}
      />
    );
  }

  const expandedTask = expandedTaskId
    ? (tasks.find((t) => t.id === expandedTaskId) ?? null)
    : null;

  return (
    <div ref={containerRef} tabIndex={-1} className="flex h-full flex-col overflow-hidden outline-none">
      <AnimatePresence mode="wait">
        {expandedTask ? (
          <TaskDetailExpanded
            key="expanded"
            ref={closeButtonRef}
            panelId={panel.i}
            task={expandedTask}
            onClose={collapse}
          />
        ) : (
          <motion.div
            key="list"
            className="dashboard-panel-scrollbar flex-1 divide-y divide-border-subtle overflow-y-auto"
          >
            {tasks.map((task) => (
              <motion.button
                key={task.id}
                layoutId={`live-task-feed-${panel.i}-${task.id}`}
                transition={shouldReduceMotion ? { duration: 0 } : panelExpandSpring}
                ref={(el) => {
                  triggerRefs.current[task.id] = el;
                }}
                onClick={() => setExpandedTaskId(task.id)}
                className="flex w-full flex-col gap-0.5 px-3 py-2 text-left transition-colors hover:bg-hover focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-brand-primary"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <Badge status={task.status} />
                  <span className="min-w-0 flex-1 truncate text-caption font-medium text-foreground">
                    {task.title}
                  </span>
                </div>
                <span className="text-caption text-muted">
                  {task.agent_id ? `agent-${task.agent_id.slice(0, 8)}` : "unassigned"}
                  {task.created_at &&
                    ` · ${formatDistanceToNow(new Date(task.created_at), { addSuffix: true })}`}
                </span>
              </motion.button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
