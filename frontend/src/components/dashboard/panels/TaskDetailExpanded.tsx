"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/Badge";
import { motion, useReducedMotion } from "framer-motion";
import { forwardRef } from "react";
import { formatDistanceToNow } from "date-fns";
import { IconClose } from "@/lib/icons";
import { panelExpandSpring } from "@/lib/motion";
import type { TaskResponse } from "@/api/generated/model";

interface Props {
  panelId: string;
  task: TaskResponse;
  onClose: () => void;
}

// Renders straight from the feed row's own TaskResponse — the list and detail
// endpoints share the same schema, so every field here is already in memory
// with no extra fetch. See tasks.py:get_task's docstring for the known gap
// (execution/bid history, tool trace, failure reasoning) that would need an
// on-demand fetch once a future endpoint extension adds those fields.
export const TaskDetailExpanded = forwardRef<HTMLButtonElement, Props>(
  function TaskDetailExpanded({ panelId, task, onClose }, closeButtonRef) {
    const shouldReduceMotion = useReducedMotion();

    return (
      <motion.div
        layoutId={`live-task-feed-${panelId}-${task.id}`}
        transition={shouldReduceMotion ? { duration: 0 } : panelExpandSpring}
        className="flex h-full flex-col gap-3 overflow-y-auto p-3"
      >
        <div className="flex shrink-0 items-start justify-between gap-2">
          <div className="min-w-0 flex-1 space-y-1.5">
            <Badge status={task.status} />
            <p className="text-label font-semibold text-foreground">{task.title}</p>
          </div>
          <Button
            ref={closeButtonRef}
            onClick={onClose}
            aria-label="Close task detail"
            variant="ghost"
            size="icon"
            className="shrink-0 rounded p-1 text-muted transition-colors hover:bg-hover hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-primary"
          >
            <IconClose size={14} />
          </Button>
        </div>

        {task.description && (
          <p className="text-caption leading-relaxed text-secondary">{task.description}</p>
        )}

        <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-caption">
          <dt className="text-muted">Agent</dt>
          <dd className="text-foreground">
            {task.agent_id ? `agent-${task.agent_id.slice(0, 8)}` : "Unassigned"}
          </dd>

          <dt className="text-muted">Task type</dt>
          <dd className="text-foreground">{task.task_type ?? "—"}</dd>

          <dt className="text-muted">Priority</dt>
          <dd className="text-foreground capitalize">{task.priority ?? "—"}</dd>

          <dt className="text-muted">Difficulty</dt>
          <dd className="text-foreground">
            {task.difficulty != null ? task.difficulty.toFixed(1) : "—"}
          </dd>

          <dt className="text-muted">Created</dt>
          <dd className="text-foreground">
            {task.created_at
              ? formatDistanceToNow(new Date(task.created_at), { addSuffix: true })
              : "—"}
          </dd>

          {task.deadline_at && (
            <>
              <dt className="text-muted">Deadline</dt>
              <dd className="text-foreground">{new Date(task.deadline_at).toLocaleString()}</dd>
            </>
          )}
        </dl>
      </motion.div>
    );
  },
);
