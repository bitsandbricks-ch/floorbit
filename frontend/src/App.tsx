import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'

// Each page is its own chunk. Flask sends only these paths to the React app (floorbit/spa.py).
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const Plugins = lazy(() => import('@/pages/Plugins'))
const Inventory = lazy(() => import('@/pages/Inventory'))
const NotFound = lazy(() => import('@/pages/NotFound'))

export default function App() {
  return (
    <Suspense fallback={null}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/settings/plugins" element={<Plugins />} />
        <Route path="/inventory" element={<Inventory />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  )
}
