import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'

// Each page is its own chunk. Flask sends only these paths to the React app (floorbit/spa.py).
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const Plugins = lazy(() => import('@/pages/Plugins'))
const Inventory = lazy(() => import('@/pages/Inventory'))
const SeatMapping = lazy(() => import('@/pages/SeatMapping'))
const Teams = lazy(() => import('@/pages/Teams'))
const SignIn = lazy(() => import('@/pages/SignIn'))
const Incidents = lazy(() => import('@/pages/Incidents'))
const HelpdeskQr = lazy(() => import('@/pages/HelpdeskQr'))
const Health = lazy(() => import('@/pages/Health'))
const Security = lazy(() => import('@/pages/Security'))
const NotFound = lazy(() => import('@/pages/NotFound'))

export default function App() {
  return (
    <Suspense fallback={null}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/settings/plugins" element={<Plugins />} />
        <Route path="/inventory" element={<Inventory />} />
        <Route path="/seat-mapping" element={<SeatMapping />} />
        <Route path="/settings/teams" element={<Teams />} />
        <Route path="/settings/sign-in" element={<SignIn />} />
        <Route path="/incidents" element={<Incidents />} />
        <Route path="/incidents/qr" element={<HelpdeskQr />} />
        <Route path="/health" element={<Health />} />
        <Route path="/security" element={<Security />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  )
}
