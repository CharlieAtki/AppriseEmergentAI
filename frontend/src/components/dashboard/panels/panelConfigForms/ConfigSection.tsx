import type { ReactNode } from "react";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
} from "@/components/ui/field";
interface ConfigSectionProps {
  label: string;
  description?: string;
  children: ReactNode;
}
export function ConfigSection({
  label,
  description,
  children,
}: ConfigSectionProps) {
  return (
    <Field>
      <FieldContent>
        <FieldLabel>{label}</FieldLabel>
        {description && <FieldDescription>{description}</FieldDescription>}
        {children}
      </FieldContent>
    </Field>
  );
}
