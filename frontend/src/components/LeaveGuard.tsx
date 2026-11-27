import { lazy, Suspense, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGuarded, wouldLose } from './useLeaveWarning'

// Only once someone is about to lose changes: every page, the public ones too, mounts this guard,
// and the dialog would bring Mantine's Modal into their first download (#1293).
const LeaveDialog = lazy(() => import('./LeaveDialog'))

/** Asks before a link inside the app leaves a page with unsaved changes (#993). The app runs on
 *  BrowserRouter, which has no navigation blocker, so this watches clicks on links: before React
 *  sees them, only while a page has something unsaved (useLeaveWarning). Mounted once, in App. */
export function LeaveGuard() {
  const navigate = useNavigate()
  const guarded = useGuarded()
  const [to, setTo] = useState<string | null>(null)

  useEffect(() => {
    if (!guarded) return
    const click = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
      const a = (e.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null
      if (!a || (a.target && a.target !== '_self') || a.hasAttribute('download')) return
      const url = new URL(a.href, window.location.href)
      if (url.origin !== window.location.origin || !wouldLose(url.pathname)) return
      e.preventDefault()
      e.stopPropagation()
      setTo(url.pathname + url.search + url.hash)
    }
    document.addEventListener('click', click, true)
    return () => document.removeEventListener('click', click, true)
  }, [guarded])

  if (to === null) return null
  return (
    <Suspense fallback={null}>
      <LeaveDialog onStay={() => setTo(null)} onGo={() => { setTo(null); navigate(to) }} />
    </Suspense>
  )
}
