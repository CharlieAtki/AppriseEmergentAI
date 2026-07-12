import type { AgentResponse } from "@/api/generated/model";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
} from "@/components/ui/field";

interface AgentMultiSelectProps {
  idPrefix: string;
  agents: AgentResponse[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  description: string;
}
export function AgentMultiSelect({
  idPrefix,
  agents,
  selectedIds,
  onToggle,
  description,
}: AgentMultiSelectProps) {
  return (
    <Field>
      <FieldContent>
        <FieldLabel>Agents</FieldLabel>
        <FieldDescription>{description}</FieldDescription>
        <div className="mt-1.5 flex max-h-32 flex-col gap-1 overflow-y-auto">
          {agents.map((agent) => (
            <Field
              key={agent.id}
              orientation="horizontal"
              className="gap-2 text-caption text-secondary"
            >
              <Checkbox
                id={`${idPrefix}-${agent.id}`}
                checked={selectedIds.includes(agent.id)}
                onCheckedChange={() => onToggle(agent.id)}
              />
              <FieldLabel htmlFor={`${idPrefix}-${agent.id}`}>{agent.name}</FieldLabel>
            </Field>
          ))}
        </div>
      </FieldContent>
    </Field>
  );
}
