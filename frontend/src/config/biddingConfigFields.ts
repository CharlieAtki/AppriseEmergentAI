export interface BiddingFieldMeta {
  key: 'bid_score_threshold'
  label: string
  description: string
  type: 'integer' | 'float'
  min?: number
  max?: number
  step?: number
}

// Rendered by both OrgSettingsModal and WorkspaceSettingsModal, as a sibling
// "Bid scoring" section next to the coordination fields — sibling config file
// to coordinationConfigFields.ts, not an extension of it, since bid-scoring
// and coordination guards are separate REST resources (see
// api/services/bidding_config_service.py's docstring for why).
export const BIDDING_CONFIG_FIELDS: BiddingFieldMeta[] = [
  {
    key: 'bid_score_threshold',
    label: 'Bid score threshold',
    description: 'Minimum score an agent’s bid must clear to be eligible for a task.',
    type: 'float',
    min: 0,
    max: 1,
    step: 0.05,
  },
]
