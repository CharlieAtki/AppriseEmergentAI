"use client";
import { useListAgentsWorkspacesWorkspaceIdAgentsGet } from "@/api/generated/agents/agents";
import type { AgentLanesConfig } from "../AgentLanesPanelBody";
import { AgentMultiSelect } from "./AgentMultiSelect";
import { ConfigSection } from "./ConfigSection";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
interface Props {
  workspaceId: string;
  config: AgentLanesConfig;
  onChange: (config: AgentLanesConfig) => void;
}
export function AgentLanesConfigForm({ workspaceId, config, onChange }: Props) {
  const { data: agents } =
    useListAgentsWorkspacesWorkspaceIdAgentsGet(workspaceId);
  const toggleAgent = (id: string) => {
    const agentIds = config.agentIds ?? [];
    onChange({
      ...config,
      agentIds: agentIds.includes(id)
        ? agentIds.filter((agentId) => agentId !== id)
        : [...agentIds, id],
    });
  };
  return (
    <div className="flex flex-col gap-3">
      <ConfigSection label="Time window">
        <Select value={config.window ?? "24h"} onValueChange={(value) => onChange({ ...config, window: value as "1h" | "6h" | "24h" })}><SelectTrigger className="mt-1 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="1h">1 hour</SelectItem><SelectItem value="6h">6 hours</SelectItem><SelectItem value="24h">24 hours</SelectItem></SelectGroup></SelectContent></Select>
      </ConfigSection>
      <ConfigSection label="Group by">
        <Select value={config.groupBy ?? "status"} onValueChange={(value) => onChange({ ...config, groupBy: value as "task" | "status" })}><SelectTrigger className="mt-1 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="status">Status</SelectItem><SelectItem value="task">Task</SelectItem></SelectGroup></SelectContent></Select>
      </ConfigSection>
      <AgentMultiSelect
        idPrefix="agent-lanes-agent"
        agents={agents ?? []}
        selectedIds={config.agentIds ?? []}
        onToggle={toggleAgent}
        description="Leave empty to show all agents as lanes."
      />
    </div>
  );
}
