import { useEffect, useState } from 'react'

interface TimeWindow {
  since: string
  nowMs: number
}

// Date.now() is impure and must not be called during render (react-hooks/purity) —
// computed in an effect instead, keyed on hours so a config change (e.g. switching
// the panel's time range) recomputes it. Panels treat `undefined` as "not ready yet"
// and disable their query until the first effect run populates it.
export function useTimeWindow(hours: number): TimeWindow | undefined {
  const [window, setWindow] = useState<TimeWindow | undefined>(undefined)

  useEffect(() => {
    const nowMs = Date.now()
    setWindow({ since: new Date(nowMs - hours * 60 * 60 * 1000).toISOString(), nowMs })
  }, [hours])

  return window
}
