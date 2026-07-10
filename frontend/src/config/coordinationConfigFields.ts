export interface ConfigFieldMeta {
  key: 'max_delegation_depth' | 'decompose_difficulty_threshold'
  label: string
  description: string
  type: 'integer' | 'float'
  min?: number
  max?: number
  step?: number
}

// Rendered by both OrgSettingsModal and WorkspaceSettingsModal — add a field
// here once the backend exposes it via CoordinationConfigResponse.
export const COORDINATION_CONFIG_FIELDS: ConfigFieldMeta[] = [
  {
    key: 'max_delegation_depth',
    label: 'Max delegation depth',
    description: 'How many levels deep a task can be decomposed into subtasks before delegation is blocked.',
    type: 'integer',
    min: 1,
    // No static max — clamped at request time to the platform's
    // max_delegation_depth_ceiling, which callers must read from the
    // CoordinationConfigResponse (it's the real, dynamic hard stop; see
    // core/coordination/config.py).
    step: 1,
  },
  {
    key: 'decompose_difficulty_threshold',
    label: 'Decompose difficulty threshold',
    description: 'Minimum difficulty score a task must reach before an agent is allowed to decompose it further.',
    type: 'float',
    min: 0,
    // No ceiling by design — a tuning knob, not a safety net.
    step: 0.1,
  },
]
