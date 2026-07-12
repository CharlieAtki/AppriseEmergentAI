import { Checkbox } from "@/components/ui/checkbox";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
} from "@/components/ui/field";

interface ChecklistOption {
  value: string;
  label: string;
}

interface ChecklistMultiSelectProps {
  idPrefix: string;
  label: string;
  description: string;
  options: ChecklistOption[];
  selected: string[];
  onToggle: (value: string) => void;
}

// Generic sibling to AgentMultiSelect — used for status/task-type/priority
// filters on the live task feed, where the option set isn't agent identity.
export function ChecklistMultiSelect({
  idPrefix,
  label,
  description,
  options,
  selected,
  onToggle,
}: ChecklistMultiSelectProps) {
  return (
    <Field>
      <FieldContent>
        <FieldLabel>{label}</FieldLabel>
        <FieldDescription>{description}</FieldDescription>
        <div className="mt-1.5 flex max-h-32 flex-col gap-1 overflow-y-auto">
          {options.map((option) => (
            <Field
              key={option.value}
              orientation="horizontal"
              className="gap-2 text-caption text-secondary"
            >
              <Checkbox
                id={`${idPrefix}-${option.value}`}
                checked={selected.includes(option.value)}
                onCheckedChange={() => onToggle(option.value)}
              />
              <FieldLabel htmlFor={`${idPrefix}-${option.value}`}>{option.label}</FieldLabel>
            </Field>
          ))}
        </div>
      </FieldContent>
    </Field>
  );
}
