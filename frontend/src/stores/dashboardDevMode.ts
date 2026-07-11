import { create } from 'zustand'

interface DashboardDevModeStore {
  enabled: boolean
  toggle: () => void
}

// Session-only UI toggle (not persisted) — lets panels preview with seeded
// mock data before a fresh workspace has accumulated real history. Global
// store rather than a prop because it needs to reach panel bodies several
// layers deep (DashboardGrid -> Canvas -> Panel -> body) without threading
// a boolean through every intermediate component.
export const useDashboardDevModeStore = create<DashboardDevModeStore>((set) => ({
  enabled: false,
  toggle: () => set((s) => ({ enabled: !s.enabled })),
}))
