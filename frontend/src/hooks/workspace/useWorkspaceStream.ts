import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { z } from 'zod'

import {
  getGetAgentWorkspacesWorkspaceIdAgentsAgentIdGetQueryKey,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
} from '@/api/generated/agents/agents'
import { AgentResponse, WorkspaceMetricsResponse } from '@/api/generated/model'
import { getListTasksWorkspacesWorkspaceIdTasksGetQueryKey } from '@/api/generated/tasks/tasks'
import {
  getGetWorkspaceMetricsWorkspacesWorkspaceIdMetricsGetQueryKey,
  mintStreamTicketWorkspacesWorkspaceIdStreamTicketPost,
} from '@/api/generated/workspaces/workspaces'

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

// Sent once on connect, before any live event — the fix for Pub/Sub's "no history"
// gap (see the Deep Dive ADR's Component 7 trade-offs). Reuses the Orval-generated
// AgentResponse and WorkspaceMetricsResponse schemas (backed by
// GET /workspaces/{id}/metrics) so both the agent pool and the metrics snapshot
// have one typed source of truth, not a hand-rolled duplicate. metrics is
// nullable — sample_metrics.py hasn't necessarily run yet for a brand-new workspace.
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
 * Connects to the workspace event stream and keeps the TanStack Query cache
 * in sync via invalidation on each event.
 *
 * Each connection attempt first mints a single-use, 30s-TTL ticket via
 * POST /workspaces/{id}/stream-ticket, then connects with ?ticket=... — the WS
 * route has no other auth path since AuthMiddleware never runs for WebSocket scope.
 */
export function useWorkspaceStream(workspaceId: string): { connected: boolean } {
  const queryClient = useQueryClient()
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let ws: WebSocket | undefined
    let retryTimeout: ReturnType<typeof setTimeout>
    let attempt = 0
    let cancelled = false

    const connect = async () => {
      // Ticket is single-use and expires in 30s — mint a fresh one on every
      // connection attempt, including reconnects, never reuse across attempts.
      let ticket: string
      try {
        ;({ ticket } = await mintStreamTicketWorkspacesWorkspaceIdStreamTicketPost(workspaceId))
      } catch {
        if (!cancelled) {
          const delay = Math.min(30000, 1000 * 2 ** attempt++)
          retryTimeout = setTimeout(connect, delay)
        }
        return
      }
      if (cancelled) return

      const wsUrl = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000'
      const url = new URL(`/workspaces/${workspaceId}/stream`, wsUrl)
      url.searchParams.set('ticket', ticket)
      ws = new WebSocket(url.toString())
      ws.onopen = () => {
        attempt = 0
        setConnected(true)
      }
      ws.onclose = () => {
        setConnected(false)
        if (!cancelled) {
          const delay = Math.min(30000, 1000 * 2 ** attempt++)
          retryTimeout = setTimeout(connect, delay)
        }
      }

      ws.onmessage = (event: MessageEvent<string>) => {
        let raw: unknown
        try {
          raw = JSON.parse(event.data)
        } catch {
          return
        }

        const result = WorkspaceEvent.safeParse(raw)
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
      }

      ws.onerror = () => {
        console.warn('[WorkspaceStream] connection error')
        setConnected(false)
      }
    }

    void connect()

    return () => {
      cancelled = true
      clearTimeout(retryTimeout)
      ws?.close()
    }
  }, [workspaceId, queryClient])

  return { connected }
}
