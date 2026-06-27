import { create } from 'zustand'

interface WorkspaceStore {
  selectedAgentId: string | null
  agentPanelOpen: boolean
  taskBoardView: 'list' | 'kanban'
  setSelectedAgent: (id: string | null) => void
  closeAgentPanel: () => void
  setTaskBoardView: (view: 'list' | 'kanban') => void
}

export const useWorkspaceStore = create<WorkspaceStore>((set) => ({
  selectedAgentId: null,
  agentPanelOpen: false,
  taskBoardView: 'list',
  setSelectedAgent: (id) => set({ selectedAgentId: id, agentPanelOpen: !!id }),
  closeAgentPanel: () => set({ selectedAgentId: null, agentPanelOpen: false }),
  setTaskBoardView: (view) => set({ taskBoardView: view }),
}))
