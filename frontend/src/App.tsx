import { lazy, Suspense } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import { PageError } from '@bitsandbricks/ui'
import { AppShell } from '@/components/Layout'
import { LeaveGuard } from '@/components/LeaveGuard'
import type { AppRoute } from '@/lib/appRoute'
import { readServerPage } from '@/lib/serverPage'

// Each page is its own chunk. Flask sends only these paths to the React app (floorbit/spa.py).
// Every area lists its pages in src/routes/<area>.ts (issue #1234): a new page is a line there, or
// a new file, never a line here. React Router picks the most specific path, so order doesn't matter.
const ROUTES = Object.values(import.meta.glob<{ routes: AppRoute[] }>('./routes/*.ts', { eager: true }))
  .flatMap((m) => m.routes)
const Forbidden = lazy(() => import('@/pages/Forbidden'))
const NotFound = lazy(() => import('@/pages/NotFound'))

// Read once: the server's answer for the page that was loaded, not for later client-side moves.
const serverPage = readServerPage()
// A 404 holds for the address it came with; a link from its sidebar moves on to a real page.
const firstPath = typeof window === 'undefined' ? '' : window.location.pathname

export default function App() {
  const { pathname } = useLocation()
  if (serverPage?.kind === 'forbidden') {
    return <PageError resetKey={pathname}><Suspense fallback={null}><Forbidden page={serverPage} /></Suspense></PageError>
  }
  if (serverPage?.kind === 'not-found' && pathname === firstPath) {
    return (
      <PageError resetKey={pathname}>
        <Suspense fallback={null}>
          <Routes><Route element={<AppShell />}><Route path="*" element={<NotFound />} /></Route></Routes>
        </Suspense>
      </PageError>
    )
  }
  return (
    // Outside the shell too (sign-in, check-in): an error there shows a way out, not a blank window.
    <PageError resetKey={pathname}>
      <LeaveGuard />
      <Suspense fallback={null}>
        <Routes>
          {ROUTES.filter((r) => r.shell === false).map((r) => <Route key={r.path} path={r.path} element={r.element} />)}
          <Route element={<AppShell />}>
            {ROUTES.filter((r) => r.shell !== false).map((r) => <Route key={r.path} path={r.path} element={r.element} />)}
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Suspense>
    </PageError>
  )
}
