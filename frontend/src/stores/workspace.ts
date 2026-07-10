import { create } from 'zustand'

interface WorkspaceStore {
  selectedAgentId: string | null
  agentPanelOpen: boolean
  taskBoardView: 'list' | 'kanban'
  // Set by useWorkspaceStream (mounted in workspaces/[workspaceId]/layout.tsx)
  // so AppHeader — a sibling of that layout under orgs/[orgId]/layout.tsx, not
  // a descendant of it — can read live connection status without a Context
  // provider positioned where it can't actually reach AppHeader.
  streamConnected: boolean
  setSelectedAgent: (id: string | null) => void
  closeAgentPanel: () => void
  setTaskBoardView: (view: 'list' | 'kanban') => void
  setStreamConnected: (connected: boolean) => void
}

export const useWorkspaceStore = create<WorkspaceStore>((set) => ({
  selectedAgentId: null,
  agentPanelOpen: false,
  taskBoardView: 'list',
  streamConnected: false,
  setSelectedAgent: (id) => set({ selectedAgentId: id, agentPanelOpen: !!id }),
  closeAgentPanel: () => set({ selectedAgentId: null, agentPanelOpen: false }),
  setTaskBoardView: (view) => set({ taskBoardView: view }),
  setStreamConnected: (connected) => set({ streamConnected: connected }),
}))
