import { useEffect, useState } from 'react'

/** An element's inner size in pixels, kept current as it changes. */
export function useSize(ref: React.RefObject<HTMLElement | null>) {
  const [px, setPx] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => setPx({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return px
}
