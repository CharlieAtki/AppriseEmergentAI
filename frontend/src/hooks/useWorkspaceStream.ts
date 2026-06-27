import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { z } from 'zod'

import {
  getGetAgentWorkspacesWorkspaceIdAgentsAgentIdGetQueryKey,
  getListAgentsWorkspacesWorkspaceIdAgentsGetQueryKey,
} from '@/api/generated/agents/agents'
import { getListTasksWorkspacesWorkspaceIdTasksGetQueryKey } from '@/api/generated/tasks/tasks'

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

export const WorkspaceEvent = z.discriminatedUnion('type', [
  TaskCompletedEvent,
  TaskExecutingEvent,
  AgentSkillUpdatedEvent,
  EmergenceDetectedEvent,
])

export type WorkspaceEvent = z.infer<typeof WorkspaceEvent>

/**
 * Connects to the workspace event stream and keeps the TanStack Query cache
 * in sync via invalidation on each event.
 *
 * `connected` reflects the live WebSocket state. It remains false until the
 * backend WS endpoint /workspaces/{id}/stream is implemented —
 * see docs/frontend/frontend-gaps.md.
 */
export function useWorkspaceStream(workspaceId: string): { connected: boolean } {
  const queryClient = useQueryClient()
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000'
    const ws = new WebSocket(`${wsUrl}/workspaces/${workspaceId}/stream`)

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)

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
      }
    }

    ws.onerror = () => {
      // Backend WS endpoint not yet implemented — see docs/frontend/frontend-gaps.md
      console.warn('[WorkspaceStream] could not connect — backend stream endpoint pending')
      setConnected(false)
    }

    return () => ws.close()
  }, [workspaceId, queryClient])

  return { connected }
}
