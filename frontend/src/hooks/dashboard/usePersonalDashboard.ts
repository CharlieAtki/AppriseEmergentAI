import { useCallback, useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { moveElement } from 'react-grid-layout'
import type { Layout } from 'react-grid-layout'
import { toast } from 'sonner'

import {
  getGetPersonalDashboardLayoutWorkspacesWorkspaceIdDashboardLayoutGetQueryKey,
  useGetPersonalDashboardLayoutWorkspacesWorkspaceIdDashboardLayoutGet,
  useSavePersonalDashboardLayoutWorkspacesWorkspaceIdDashboardLayoutPut,
} from '@/api/generated/personal-dashboard/personal-dashboard'
import type { PersonalDashboardLayoutRequest, PersonalDashboardLayoutResponse } from '@/api/generated/model'
import { findFreeSlot, GRID_ROWS } from '@/lib/dashboardGrid'
import { getPanelDefinition } from '@/lib/dashboardPanels'
import type { DashboardPanelInstance, PersonalDashboardLayout } from '@/lib/personalDashboard'

const SAVE_DELAY_MS = 750
const EMPTY_LAYOUT: PersonalDashboardLayout = { pages: [[]], activePage: 0 }

function fromResponse(response: PersonalDashboardLayoutResponse): PersonalDashboardLayout {
  return {
    pages: response.pages.map((page) =>
      page.map((panel) => ({
        i: panel.id,
        x: panel.x,
        y: panel.y,
        w: panel.w,
        h: panel.h,
        minW: panel.min_w,
        minH: panel.min_h,
        panelType: panel.panel_type,
        config: panel.config ?? {},
      })),
    ),
    activePage: response.active_page,
  }
}

function toRequest(layout: PersonalDashboardLayout): PersonalDashboardLayoutRequest {
  return {
    pages: layout.pages.map((page) =>
      page.map((panel) => ({
        id: panel.i,
        panel_type: panel.panelType as PersonalDashboardLayoutRequest['pages'][number][number]['panel_type'],
        x: panel.x,
        y: panel.y,
        w: panel.w,
        h: panel.h,
        min_w: panel.minW ?? 1,
        min_h: panel.minH ?? 1,
        config: panel.config,
      })),
    ),
    active_page: layout.activePage,
  }
}

function withTypes(layout: Layout, previous: DashboardPanelInstance[]): DashboardPanelInstance[] {
  const byId = new Map(previous.map((panel) => [panel.i, panel]))
  return layout.map((item) => {
    const prev = byId.get(item.i)
    const unchanged =
      prev &&
      prev.x === item.x &&
      prev.y === item.y &&
      prev.w === item.w &&
      prev.h === item.h &&
      prev.minW === item.minW &&
      prev.minH === item.minH
    return unchanged ? prev : { ...item, panelType: prev?.panelType ?? 'unknown', config: prev?.config ?? {} }
  })
}

export function usePersonalDashboard(workspaceId: string) {
  const queryClient = useQueryClient()
  const queryKey = getGetPersonalDashboardLayoutWorkspacesWorkspaceIdDashboardLayoutGetQueryKey(workspaceId)
  const query = useGetPersonalDashboardLayoutWorkspacesWorkspaceIdDashboardLayoutGet(workspaceId)
  const save = useSavePersonalDashboardLayoutWorkspacesWorkspaceIdDashboardLayoutPut()
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingRef = useRef<PersonalDashboardLayout | null>(null)
  const savingRef = useRef(false)
  const confirmedRef = useRef<PersonalDashboardLayout>(EMPTY_LAYOUT)
  const mutateAsync = save.mutateAsync
  const refetch = query.refetch

  useEffect(() => {
    window.localStorage.removeItem('apprise-dashboard-layout')
  }, [])

  useEffect(() => {
    if (query.data) confirmedRef.current = fromResponse(query.data)
  }, [query.data])

  // The save queue intentionally recurses after an in-flight mutation settles.
  // eslint-disable-next-line react-hooks/preserve-manual-memoization
  const persist = useCallback(async () => {
    if (savingRef.current || !pendingRef.current) return
    const snapshot = pendingRef.current
    pendingRef.current = null
    savingRef.current = true
    try {
      const response = await mutateAsync({ workspaceId, data: toRequest(snapshot) })
      confirmedRef.current = fromResponse(response)
      if (!pendingRef.current) queryClient.setQueryData(queryKey, response)
    } catch {
      toast.error('Could not save dashboard changes. Restoring the last saved layout.')
      if (!pendingRef.current) {
        queryClient.setQueryData(queryKey, {
          pages: confirmedRef.current.pages.map((page) =>
            page.map((panel) => ({
              id: panel.i,
              panel_type: panel.panelType,
              x: panel.x,
              y: panel.y,
              w: panel.w,
              h: panel.h,
              min_w: panel.minW ?? 1,
              min_h: panel.minH ?? 1,
              config: panel.config,
            })),
          ),
          active_page: confirmedRef.current.activePage,
          updated_at: null,
        } as PersonalDashboardLayoutResponse)
        void refetch()
      }
    } finally {
      savingRef.current = false
      if (pendingRef.current) void persist()
    }
  }, [mutateAsync, queryClient, queryKey, refetch, workspaceId])

  const update = useCallback(
    (transform: (layout: PersonalDashboardLayout) => PersonalDashboardLayout) => {
      const current = queryClient.getQueryData<PersonalDashboardLayoutResponse>(queryKey)
      const next = transform(current ? fromResponse(current) : EMPTY_LAYOUT)
      const response = {
        pages: toRequest(next).pages,
        active_page: next.activePage,
        updated_at: null,
      } as PersonalDashboardLayoutResponse
      queryClient.setQueryData(queryKey, response)
      pendingRef.current = next
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => void persist(), SAVE_DELAY_MS)
    },
    [persist, queryClient, queryKey],
  )

  const setActivePage = useCallback((activePage: number) => update((layout) => ({ ...layout, activePage })), [update])
  const addPanel = useCallback((panelType: string) => update((layout) => {
    const definition = getPanelDefinition(panelType)
    const pages = layout.pages.map((page) => [...page])
    for (let pageIndex = layout.activePage; pageIndex < pages.length; pageIndex++) {
      const slot = findFreeSlot(pages[pageIndex]!, definition.defaultW, definition.defaultH)
      if (!slot) continue
      pages[pageIndex]!.push({ i: crypto.randomUUID(), x: slot.x, y: slot.y, w: definition.defaultW, h: definition.defaultH, minW: definition.minW, minH: definition.minH, panelType, config: {} })
      return { pages, activePage: pageIndex }
    }
    return { pages: [...pages, [{ i: crypto.randomUUID(), x: 0, y: 0, w: definition.defaultW, h: definition.defaultH, minW: definition.minW, minH: definition.minH, panelType, config: {} }]], activePage: pages.length }
  }), [update])
  const removePanel = useCallback((id: string) => update((layout) => {
    const pageIndex = layout.pages.findIndex((page) => page.some((panel) => panel.i === id))
    if (pageIndex === -1) return layout
    const pages = layout.pages.map((page) => page.filter((panel) => panel.i !== id))
    if (pages[pageIndex]!.length === 0 && pages.length > 1) {
      pages.splice(pageIndex, 1)
      return { pages, activePage: Math.min(layout.activePage >= pageIndex ? Math.max(0, layout.activePage - 1) : layout.activePage, pages.length - 1) }
    }
    return { pages, activePage: layout.activePage }
  }), [update])
  const setLayout = useCallback((pageIndex: number, gridLayout: Layout) => update((layout) => {
    const pages = [...layout.pages]
    pages[pageIndex] = withTypes(gridLayout, pages[pageIndex] ?? [])
    return { ...layout, pages }
  }), [update])
  const movePanel = useCallback((pageIndex: number, id: string, dx: number, dy: number, cols: number) => update((layout) => {
    const panels = layout.pages[pageIndex] ?? []
    const item = panels.find((panel) => panel.i === id)
    if (!item) return layout
    const moved = moveElement(panels, item, Math.max(0, Math.min(cols - item.w, item.x + dx)), Math.max(0, Math.min(GRID_ROWS - item.h, item.y + dy)), true, false, 'vertical', cols)
    const pages = [...layout.pages]
    pages[pageIndex] = withTypes(moved, panels)
    return { ...layout, pages }
  }), [update])
  const updatePanelConfig = useCallback((pageIndex: number, id: string, config: Record<string, unknown>) => update((layout) => {
    const pages = [...layout.pages]
    pages[pageIndex] = (pages[pageIndex] ?? []).map((panel) => panel.i === id ? { ...panel, config: { ...panel.config, ...config } } : panel)
    return { ...layout, pages }
  }), [update])

  const layout = query.data ? fromResponse(query.data) : EMPTY_LAYOUT
  return { ...layout, isLoading: query.isLoading, isError: query.isError, setActivePage, addPanel, removePanel, setLayout, movePanel, updatePanelConfig }
}
