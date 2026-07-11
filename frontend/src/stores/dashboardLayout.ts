import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { moveElement } from 'react-grid-layout'
import type { Layout, LayoutItem } from 'react-grid-layout'
import { getPanelDefinition } from '@/lib/dashboardPanels'
import { findFreeSlot, GRID_ROWS } from '@/lib/dashboardGrid'

export interface DashboardPanelInstance extends LayoutItem {
  panelType: string
}

interface DashboardLayoutStore {
  pages: DashboardPanelInstance[][]
  activePage: number
  setActivePage: (page: number) => void
  addPanel: (panelType: string) => void
  removePanel: (id: string) => void
  setLayout: (pageIndex: number, layout: Layout) => void
  movePanel: (pageIndex: number, id: string, dx: number, dy: number, cols: number) => void
}

// Reuses the previous item's object reference when nothing about it actually
// changed, so React.memo on DashboardPanel can skip re-rendering panels that
// weren't the one dragged/resized/moved — RGL's own layout output otherwise
// rebuilds every item's object on every change, defeating memoization.
function withTypes(layout: Layout, previous: DashboardPanelInstance[]): DashboardPanelInstance[] {
  const byId = new Map(previous.map((panel) => [panel.i, panel]))
  return layout.map((item) => {
    const prev = byId.get(item.i)
    const unchanged =
      prev && prev.x === item.x && prev.y === item.y && prev.w === item.w && prev.h === item.h && prev.minW === item.minW && prev.minH === item.minH
    return unchanged ? prev : { ...item, panelType: prev?.panelType ?? 'unknown' }
  })
}

// Stub: layout persists client-side only (zustand + localStorage). Backend
// persistence (per-workspace, via core/models + api/ service) is a follow-up
// once the grid mechanic is validated.
export const useDashboardLayoutStore = create<DashboardLayoutStore>()(
  persist(
    (set, get) => ({
      pages: [[]],
      activePage: 0,

      setActivePage: (page) => set({ activePage: page }),

      addPanel: (panelType) => {
        const definition = getPanelDefinition(panelType)
        const { pages, activePage } = get()

        const buildItem = (x: number, y: number): DashboardPanelInstance => ({
          i: `${panelType}-${crypto.randomUUID()}`,
          x,
          y,
          w: definition.defaultW,
          h: definition.defaultH,
          minW: definition.minW,
          minH: definition.minH,
          panelType,
        })

        // Try the active page first, then later pages in order — reuses
        // existing free space on a page the user's already created before
        // spilling onto a brand new one.
        for (let pageIndex = activePage; pageIndex < pages.length; pageIndex++) {
          const panels = pages[pageIndex]!
          const slot = findFreeSlot(panels, definition.defaultW, definition.defaultH)
          if (!slot) continue

          const nextPages = [...pages]
          nextPages[pageIndex] = [...panels, buildItem(slot.x, slot.y)]
          set({ pages: nextPages, activePage: pageIndex })
          return
        }

        // No room on the active page or any page after it: create a new one.
        set({ pages: [...pages, [buildItem(0, 0)]], activePage: pages.length })
      },

      removePanel: (id) => {
        const { pages, activePage } = get()
        const pageIndex = pages.findIndex((page) => page.some((panel) => panel.i === id))
        if (pageIndex === -1) return

        const nextPages = pages.map((page) => page.filter((panel) => panel.i !== id))
        const becameEmpty = nextPages[pageIndex]!.length === 0

        if (becameEmpty && nextPages.length > 1) {
          nextPages.splice(pageIndex, 1)
          const nextActive = Math.min(activePage >= pageIndex ? Math.max(0, activePage - 1) : activePage, nextPages.length - 1)
          set({ pages: nextPages, activePage: nextActive })
        } else {
          set({ pages: nextPages })
        }
      },

      setLayout: (pageIndex, layout) => {
        const { pages } = get()
        const current = pages[pageIndex] ?? []
        const nextPages = [...pages]
        nextPages[pageIndex] = withTypes(layout, current)
        set({ pages: nextPages })
      },

      movePanel: (pageIndex, id, dx, dy, cols) => {
        const { pages } = get()
        const panels = pages[pageIndex] ?? []
        const item = panels.find((panel) => panel.i === id)
        if (!item) return

        const x = Math.max(0, Math.min(cols - item.w, item.x + dx))
        const y = Math.max(0, Math.min(GRID_ROWS - item.h, item.y + dy))
        const moved = moveElement(panels, item, x, y, true, false, 'vertical', cols)

        const nextPages = [...pages]
        nextPages[pageIndex] = withTypes(moved, panels)
        set({ pages: nextPages })
      },
    }),
    {
      name: 'apprise-dashboard-layout',
      // v0 persisted a flat `panels[]`; v1 introduced multi-page `pages[][]`.
      // Old localStorage data doesn't have a `pages` key, so zustand's default
      // shallow merge would silently keep the fresh-store default instead of
      // surfacing an error — discard it explicitly instead of leaving stray
      // `panels` data sitting unused alongside an empty `pages`.
      version: 1,
      migrate: (_persistedState, version) => {
        if (version < 1) return { pages: [[]], activePage: 0 }
        return _persistedState as Pick<DashboardLayoutStore, 'pages' | 'activePage'>
      },
    },
  ),
)
