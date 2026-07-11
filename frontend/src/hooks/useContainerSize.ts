'use client'

import { useEffect, useRef, useState } from 'react'

interface ContainerSize {
  width: number
  height: number
}

// react-grid-layout's own useContainerWidth only measures width; the fixed
// 12x7 canvas needs height too, to derive a rowHeight that fills exactly 7
// rows with no scroll.
export function useContainerSize<T extends HTMLElement>() {
  const containerRef = useRef<T>(null)
  const [size, setSize] = useState<ContainerSize>({ width: 0, height: 0 })
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    const node = containerRef.current
    if (!node) return

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      const { width, height } = entry.contentRect
      setSize({ width, height })
    })

    observer.observe(node)
    setSize({ width: node.clientWidth, height: node.clientHeight })
    setMounted(true)

    return () => observer.disconnect()
  }, [])

  return { containerRef, width: size.width, height: size.height, mounted }
}
