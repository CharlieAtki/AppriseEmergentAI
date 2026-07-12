"use client";
import { useListAgentsWorkspacesWorkspaceIdAgentsGet } from "@/api/generated/agents/agents";
import type { AgentPoolConfig } from "../AgentPoolPanelBody";
import { AgentMultiSelect } from "./AgentMultiSelect";
import { ConfigSection } from "./ConfigSection";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
interface Props {
  workspaceId: string;
  config: AgentPoolConfig;
  onChange: (config: AgentPoolConfig) => void;
}
export function AgentPoolConfigForm({ workspaceId, config, onChange }: Props) {
  const { data: agents } =
    useListAgentsWorkspacesWorkspaceIdAgentsGet(workspaceId);
  const windowMode = config.windowMode ?? "calendar";
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
      <ConfigSection label="Sort">
        <Select value={config.sort ?? "influence"} onValueChange={(value) => onChange({ ...config, sort: value as "influence" | "name" })}><SelectTrigger className="mt-1 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="influence">Influence</SelectItem><SelectItem value="name">Name</SelectItem></SelectGroup></SelectContent></Select>
      </ConfigSection>
      <ConfigSection label="Trend window">
        <ToggleGroup value={[windowMode]} onValueChange={(values) => values[0] && onChange({ ...config, windowMode: values[0] as "calendar" | "last-n" })} spacing={1} className="mt-1 w-full"><ToggleGroupItem value="calendar" className="flex-1">Calendar</ToggleGroupItem><ToggleGroupItem value="last-n" className="flex-1">Last N points</ToggleGroupItem></ToggleGroup>{windowMode === "calendar" ? (<Select value={config.calendarRange ?? "24h"} onValueChange={(value) => onChange({ ...config, calendarRange: value as "24h" | "7d" | "30d" })}><SelectTrigger className="mt-1.5 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="24h">24 hours</SelectItem><SelectItem value="7d">7 days</SelectItem><SelectItem value="30d">30 days</SelectItem></SelectGroup></SelectContent></Select>) : (<Input className="mt-1.5" type="number" min={1} max={50} value={config.lastN ?? 5} onChange={(event) => onChange({ ...config, lastN: Number(event.target.value) })} />)}
      </ConfigSection>
      <AgentMultiSelect
        idPrefix="agent-pool-agent"
        agents={agents ?? []}
        selectedIds={config.agentIds ?? []}
        onToggle={toggleAgent}
        description="Leave empty to show all, sorted and sized to fit."
      />
    </div>
  );
}
