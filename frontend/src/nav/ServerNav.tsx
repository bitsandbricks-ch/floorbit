import { useEffect, useState } from 'react'
import { readBoot } from './boot'
import { Sidebar, type LinkProps } from './Sidebar'

declare global {
  interface Window { floorGoTo?: { open: () => void } }
}

const plain = ({ children, ...rest }: LinkProps) => <a {...rest}>{children}</a>

/** Switches down, for the badge next to Problems; the floor plan asks for the same list anyway. */
function useDown(): number | null {
  const [down, setDown] = useState<number | null>(null)
  useEffect(() => {
    let stop = false
    const load = () => {
      if (document.hidden) return
      fetch('/api/problems', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .then((r) => (r.ok ? r.json() : null))
        .then((b: { counts?: { down?: number } } | null) => { if (!stop && b) setDown(b.counts?.down ?? 0) })
        .catch(() => { /* extra information only */ })
    }
    load()
    const timer = setInterval(load, 30_000)
    return () => { stop = true; clearInterval(timer) }
  }, [])
  return down
}

/** The sidebar on a page Flask draws: plain links, and the page's own Go to (static/js/goto.js). */
export function ServerNav() {
  const boot = readBoot()
  const down = useDown()
  return (
    <Sidebar
      boot={boot} path={window.location.pathname} renderLink={plain} down={down}
      onGoTo={() => window.floorGoTo?.open()}
    />
  )
}
