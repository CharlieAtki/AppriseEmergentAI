"use client";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldContent, FieldLabel } from "@/components/ui/field";
import type { EmergenceSignalConfig } from "../EmergenceSignalPanelBody";
import { ConfigSection } from "./ConfigSection";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
interface Props {
  config: EmergenceSignalConfig;
  onChange: (config: EmergenceSignalConfig) => void;
}
export function EmergenceSignalConfigForm({ config, onChange }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <ConfigSection label="Time range">
        <Select value={config.timeRange ?? "24h"} onValueChange={(value) => onChange({ ...config, timeRange: value as "24h" | "7d" | "30d" | "90d" })}><SelectTrigger className="mt-1 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectGroup><SelectItem value="24h">24 hours</SelectItem><SelectItem value="7d">7 days</SelectItem><SelectItem value="30d">30 days</SelectItem><SelectItem value="90d">90 days</SelectItem></SelectGroup></SelectContent></Select>
      </ConfigSection>
      <Field
        orientation="horizontal"
        className="gap-2 text-caption text-secondary"
      >
        <Checkbox
          id="emergence-signal-show-hub-markers"
          checked={config.showHubMarkers ?? true}
          onCheckedChange={(checked) =>
            onChange({ ...config, showHubMarkers: checked })
          }
        />
        <FieldContent>
          <FieldLabel htmlFor="emergence-signal-show-hub-markers">
            Show hub-detection markers
          </FieldLabel>
        </FieldContent>
      </Field>
    </div>
  );
}
