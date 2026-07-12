"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { useListTasksWorkspacesWorkspaceIdTasksGet } from "@/api/generated/tasks/tasks";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/skeleton";
import { mockTaskFeed } from "@/lib/devMockData";
import { useDashboardDevModeStore } from "@/stores/dashboardDevMode";
import type { DashboardPanelInstance } from "@/stores/dashboardLayout";
import { PanelEmptyState } from "./PanelEmptyState";
import { TaskDetailExpanded } from "./TaskDetailExpanded";

interface LiveTaskFeedPanelBodyProps {
  workspaceId: string;
  panel: DashboardPanelInstance;
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

  // Date.now() is impure and must not be called during render (react-hooks/purity)
  // — computed in an effect, same pattern as useTimeWindow. Only needed for the
  // mock feed's relative timestamps; undefined just means "not ready yet".
  const [nowMs, setNowMs] = useState<number | undefined>(undefined);
  useEffect(() => {
    setNowMs(Date.now());
  }, []);

  const { data: fetchedTasks } = useListTasksWorkspacesWorkspaceIdTasksGet(
    workspaceId,
    { limit: FEED_LIMIT },
    { query: { enabled: !devMode } },
  );
  const tasks = devMode && nowMs !== undefined ? mockTaskFeed(nowMs, FEED_LIMIT) : fetchedTasks;
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
    return <PanelEmptyState message="No tasks in this workspace yet." />;
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
            className="flex-1 divide-y divide-border-subtle overflow-y-auto"
          >
            {tasks.map((task) => (
              <motion.button
                key={task.id}
                layoutId={`live-task-feed-${panel.i}-${task.id}`}
                transition={
                  shouldReduceMotion
                    ? { duration: 0 }
                    : { type: "spring", damping: 30, stiffness: 300 }
                }
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
