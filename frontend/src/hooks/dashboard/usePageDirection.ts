'use client'

import { useState } from 'react'

interface PageDirectionState {
  page: number
  direction: number
}

// Derives the slide direction (+1 forward, -1 back) from a page number
// change, using React's "adjust state during render" pattern rather than a
// ref or an effect — so it's correct on the very same render, regardless of
// whether the page changed via manual pagination or a store-driven side
// effect (e.g. auto-collapsing an emptied page).
export function usePageDirection(page: number): number {
  const [state, setState] = useState<PageDirectionState>({ page, direction: 0 })
  if (page !== state.page) {
    setState({ page, direction: page > state.page ? 1 : -1 })
  }
  return state.direction
}
