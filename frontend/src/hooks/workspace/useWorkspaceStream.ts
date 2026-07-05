import { useAuth } from '@clerk/nextjs'
import { useQueryClient } from '@tanstack/react-query'
import { Centrifuge } from 'centrifuge'
import { useEffect, useRef, useState } from 'react'
import { z } from 'zod'

import {
  getGetAgentWorkspacesWorkspaceIdAgentsAgentIdGetQueryKey,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
} from '@/api/generated/agents/agents'
import { AgentResponse, WorkspaceMetricsResponse } from '@/api/generated/model'
import { getListTasksWorkspacesWorkspaceIdTasksGetQueryKey } from '@/api/generated/tasks/tasks'
import { getGetWorkspaceMetricsWorkspacesWorkspaceIdMetricsGetQueryKey } from '@/api/generated/workspaces/workspaces'
import { useToastStore } from '@/stores/toast'

const TaskCompletedEvent = z.object({
  type: z.literal('task.completed'),
  task_id: z.string(),
  agent_id: z.string(),
  quality_score: z.number().min(0).max(1),
})

const TaskExecutingEvent = z.object({
  type: z.literal('task.executing'),
  task_id: z.string(),
  agent_id: z.string(),
})

const AgentSkillUpdatedEvent = z.object({
  type: z.literal('agent.skill_updated'),
  agent_id: z.string(),
  skill_deltas: z.record(z.string(), z.number()),
  new_influence: z.number(),
})

const EmergenceDetectedEvent = z.object({
  type: z.literal('emergence.detected'),
  gini_coefficient: z.number(),
  hub_agent_id: z.string(),
})

// Sent once, as the subscribe-proxy response's `data` field (backend/api/api/routers/
// centrifugo_proxy.py) — the fix for Pub/Sub's "no history" gap (see the Deep Dive
// ADR's Component 7 trade-offs). Reuses the Orval-generated AgentResponse and
// WorkspaceMetricsResponse schemas (backed by GET /workspaces/{id}/metrics) so both
// the agent pool and the metrics snapshot have one typed source of truth, not a
// hand-rolled duplicate. metrics is nullable — sample_metrics.py hasn't necessarily
// run yet for a brand-new workspace.
const WorkspaceInitEvent = z.object({
  type: z.literal('init'),
  agents: z.array(AgentResponse),
  metrics: WorkspaceMetricsResponse.nullable(),
})

export const WorkspaceEvent = z.discriminatedUnion('type', [
  TaskCompletedEvent,
  TaskExecutingEvent,
  AgentSkillUpdatedEvent,
  EmergenceDetectedEvent,
  WorkspaceInitEvent,
])

export type WorkspaceEvent = z.infer<typeof WorkspaceEvent>

/**
 * Connects to the workspace event stream (via Centrifugo) and keeps the
 * TanStack Query cache in sync via invalidation on each event.
 *
 * Auth is a connect/subscribe proxy round trip into the API process
 * (backend/api/api/routers/centrifugo_proxy.py), not a bearer token on the
 * socket — the Clerk session token rides in `getData`, forwarded into the
 * connect-proxy request's `data` field. Reconnect/backoff/heartbeat are all
 * owned by the `centrifuge` client, not hand-rolled here.
 */
export function useWorkspaceStream(workspaceId: string): { connected: boolean } {
  const queryClient = useQueryClient()
  const { getToken } = useAuth()
  const [connected, setConnected] = useState(false)

  // Clerk's getToken identity is not stable across renders — read it via a ref
  // inside getData rather than the effect's dependency array, so a render that
  // just gives us a new getToken reference doesn't tear down and reconnect the
  // whole Centrifuge client.
  const getTokenRef = useRef(getToken)
  getTokenRef.current = getToken

  useEffect(() => {
    const configuredUrl = process.env.NEXT_PUBLIC_CENTRIFUGO_URL
    if (!configuredUrl && process.env.NODE_ENV !== 'development') {
      // NEXT_PUBLIC_ vars are inlined at build time — a missing value here means
      // this build was never configured with a real Centrifugo URL. Silently
      // falling back to localhost would have every browser in a deployed
      // environment fail to connect with no indication why; fail loudly instead.
      throw new Error(
        'NEXT_PUBLIC_CENTRIFUGO_URL is not set. Required outside local development.',
      )
    }
    const url = configuredUrl ?? 'ws://localhost:8001/connection/websocket'
    const centrifuge = new Centrifuge(url, {
      getData: async () => ({ clerkToken: await getTokenRef.current() }),
    })

    centrifuge.on('connected', () => setConnected(true))
    centrifuge.on('disconnected', () => setConnected(false))

    const sub = centrifuge.newSubscription(`workspace:${workspaceId}:events`)

    sub.on('publication', (ctx: { data: unknown }) => {
      const result = WorkspaceEvent.safeParse(ctx.data)
      if (!result.success) return

      const e = result.data

      switch (e.type) {
        case 'task.completed':
        case 'task.executing':
          void queryClient.invalidateQueries({
            queryKey: getListTasksWorkspacesWorkspaceIdTasksGetQueryKey(workspaceId),
          })
          break
        case 'agent.skill_updated':
          void queryClient.invalidateQueries({
            queryKey: getGetAgentWorkspacesWorkspaceIdAgentsAgentIdGetQueryKey(
              workspaceId,
              e.agent_id,
            ),
          })
          void queryClient.invalidateQueries({
            queryKey: getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey(workspaceId),
          })
          break
        case 'emergence.detected':
          // Ephemeral, non-fetchable signal — a toast, not TanStack Query state
          // (nothing to invalidate against) and not Zustand (CLAUDE.md: never put
          // API/WebSocket data in a Zustand store). A persistent history view would
          // be a proper REST-backed query resource, not this.
          useToastStore.getState().toast({
            title: 'Emergence detected',
            description: `Hub agent detected (gini ${e.gini_coefficient.toFixed(2)})`,
          })
          break
        case 'init':
          // Complete state, not a delta — setQueryData per the ADR's own rule
          // (invalidateQueries would just force a redundant refetch of what
          // this message already carries).
          queryClient.setQueryData(
            getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey(workspaceId),
            e.agents,
          )
          if (e.metrics) {
            queryClient.setQueryData(
              getGetWorkspaceMetricsWorkspacesWorkspaceIdMetricsGetQueryKey(workspaceId),
              e.metrics,
            )
          }
          break
      }
    })

    sub.subscribe()
    centrifuge.connect()

    return () => {
      centrifuge.disconnect()
    }
  }, [workspaceId, queryClient])

  return { connected }
}
