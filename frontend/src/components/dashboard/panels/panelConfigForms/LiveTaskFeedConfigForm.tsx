"use client";
import { useMemo } from "react";
import { useListAgentsWorkspacesWorkspaceIdAgentsGet } from "@/api/generated/agents/agents";
import { useListTasksWorkspacesWorkspaceIdTasksGet } from "@/api/generated/tasks/tasks";
import { TaskStatus } from "@/api/generated/model/taskStatus.zod";
import { TaskPriority } from "@/api/generated/model/taskPriority.zod";
import { STATUS_CHART_LEGEND } from "@/lib/chartColors";
import type { LiveTaskFeedConfig } from "../LiveTaskFeedPanelBody";
import { AgentMultiSelect } from "./AgentMultiSelect";
import { ChecklistMultiSelect } from "./ChecklistMultiSelect";
import { ConfigSection } from "./ConfigSection";
import { Input } from "@/components/ui/input";

interface Props {
  workspaceId: string;
  config: LiveTaskFeedConfig;
  onChange: (config: LiveTaskFeedConfig) => void;
}

const STATUS_LABELS = new Map(STATUS_CHART_LEGEND.map(({ status, label }) => [status, label]));

function toggleValue(values: string[] | undefined, value: string): string[] {
  const current = values ?? [];
  return current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
}

export function LiveTaskFeedConfigForm({ workspaceId, config, onChange }: Props) {
  const { data: agents } = useListAgentsWorkspacesWorkspaceIdAgentsGet(workspaceId);
  const { data: tasks } = useListTasksWorkspacesWorkspaceIdTasksGet(workspaceId, { limit: 50 });

  const taskTypeOptions = useMemo(() => {
    const distinct = new Set((tasks ?? []).map((t) => t.task_type).filter((t): t is string => !!t));
    return Array.from(distinct)
      .sort()
      .map((value) => ({ value, label: value }));
  }, [tasks]);

  return (
    <div className="flex flex-col gap-3">
      <ConfigSection label="Max visible rows" description="Bounded by the 50-row feed fetch.">
        <Input
          className="mt-1"
          type="number"
          min={1}
          max={50}
          value={config.maxVisible ?? 50}
          onChange={(event) => onChange({ ...config, maxVisible: Number(event.target.value) })}
        />
      </ConfigSection>
      <AgentMultiSelect
        idPrefix="live-feed-agent"
        agents={agents ?? []}
        selectedIds={config.agentIds ?? []}
        onToggle={(id) => onChange({ ...config, agentIds: toggleValue(config.agentIds, id) })}
        description="Leave empty to show tasks from every agent."
      />
      <ChecklistMultiSelect
        idPrefix="live-feed-status"
        label="Status"
        description="Leave empty to show every status."
        options={TaskStatus.options.map((status) => ({ value: status, label: STATUS_LABELS.get(status) ?? status }))}
        selected={config.statuses ?? []}
        onToggle={(status) => onChange({ ...config, statuses: toggleValue(config.statuses, status) })}
      />
      <ChecklistMultiSelect
        idPrefix="live-feed-priority"
        label="Priority"
        description="Leave empty to show every priority."
        options={TaskPriority.options.map((priority) => ({
          value: priority,
          label: priority.charAt(0).toUpperCase() + priority.slice(1),
        }))}
        selected={config.priorities ?? []}
        onToggle={(priority) => onChange({ ...config, priorities: toggleValue(config.priorities, priority) })}
      />
      {taskTypeOptions.length > 0 && (
        <ChecklistMultiSelect
          idPrefix="live-feed-task-type"
          label="Task type"
          description="Leave empty to show every task type."
          options={taskTypeOptions}
          selected={config.taskTypes ?? []}
          onToggle={(taskType) => onChange({ ...config, taskTypes: toggleValue(config.taskTypes, taskType) })}
        />
      )}
    </div>
  );
}
