'use client'

import type { EmergenceSignalConfig } from '../EmergenceSignalPanelBody'

interface EmergenceSignalConfigFormProps {
  config: EmergenceSignalConfig
  onChange: (config: EmergenceSignalConfig) => void
}

export function EmergenceSignalConfigForm({ config, onChange }: EmergenceSignalConfigFormProps) {
  return (
    <div className="flex flex-col gap-3">
      <div>
        <label className="text-caption font-semibold uppercase tracking-architectural text-muted">Time range</label>
        <select
          value={config.timeRange ?? '24h'}
          onChange={(e) => onChange({ ...config, timeRange: e.target.value as '24h' | '7d' | '30d' | '90d' })}
          className="mt-1 w-full rounded-md border border-border bg-elevated px-2 py-1.5 text-body text-foreground"
        >
          <option value="24h">24 hours</option>
          <option value="7d">7 days</option>
          <option value="30d">30 days</option>
          <option value="90d">90 days</option>
        </select>
      </div>

      <label className="flex items-center gap-2 text-caption text-secondary">
        <input
          type="checkbox"
          checked={config.showHubMarkers ?? true}
          onChange={(e) => onChange({ ...config, showHubMarkers: e.target.checked })}
        />
        Show hub-detection markers
      </label>
    </div>
  )
}
