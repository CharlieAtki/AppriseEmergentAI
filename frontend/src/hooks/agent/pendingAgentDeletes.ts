const pendingCountByWorkspace = new Map<string, number>()

export function markAgentDeletePending(workspaceId: string): void {
  pendingCountByWorkspace.set(workspaceId, (pendingCountByWorkspace.get(workspaceId) ?? 0) + 1)
}

export function clearAgentDeletePending(workspaceId: string): void {
  const count = pendingCountByWorkspace.get(workspaceId) ?? 0
  if (count <= 1) {
    pendingCountByWorkspace.delete(workspaceId)
  } else {
    pendingCountByWorkspace.set(workspaceId, count - 1)
  }
}

export function isAgentDeletePending(workspaceId: string): boolean {
  return (pendingCountByWorkspace.get(workspaceId) ?? 0) > 0
}
