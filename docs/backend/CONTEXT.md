# Backend

Multi-tenant agent platform. Agents specialise through task execution; ContractNet bidding determines which agent handles each task. PostgreSQL is the source of truth.

## Language

### Observability

**Personal Dashboard**:
A user's private arrangement and configuration of observability panels for one workspace. It controls presentation only; it is not workspace-wide coordination or bidding configuration.
_Avoid_: "workspace dashboard" when referring to a user's saved layout, "personalisation" for the workspace's operational configuration.

**Workspace Metrics Snapshot**:
A routine, periodic sample of workspace-wide statistics (Gini coefficient over agent influence, specialisation index, agent count), written every `sample_metrics` cron tick (~15s) for every active workspace with â‰¥2 agents. Always written, regardless of whether anything notable occurred.
_Avoid_: "workspace metrics" alone (ambiguous with Emergence Event, below), "metrics" alone.

**Emergence Event**:
A discrete, notable occurrence — currently only "a hub agent was detected" — written to `emergence_events` only when the condition is met, not on every sample tick. Carries a `gini_coefficient` at the time of detection and the `hub_agent_id`, but is a different write cadence and a different domain concept from a Workspace Metrics Snapshot even though both reference Gini.
_Avoid_: "metrics event", conflating with Workspace Metrics Snapshot.
