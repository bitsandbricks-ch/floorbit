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
const Power = lazy(() => import('@/pages/Power'))
const Problems = lazy(() => import('@/pages/Problems'))
const Setup = lazy(() => import('@/pages/Setup'))
const Stats = lazy(() => import('@/pages/Stats'))
const Traffic = lazy(() => import('@/pages/Traffic'))
const Dns = lazy(() => import('@/pages/Dns'))
const Games = lazy(() => import('@/pages/Games'))
const Logs = lazy(() => import('@/pages/Logs'))
const Templates = lazy(() => import('@/pages/Templates'))
const Replay = lazy(() => import('@/pages/Replay'))
const Report = lazy(() => import('@/pages/Report'))
const Jobs = lazy(() => import('@/pages/Jobs'))
const Tournament = lazy(() => import('@/pages/Tournament'))
const Handover = lazy(() => import('@/pages/Handover'))
const Planner = lazy(() => import('@/pages/Planner'))
const Preflight = lazy(() => import('@/pages/Preflight'))
const Gear = lazy(() => import('@/pages/Gear'))
const Teardown = lazy(() => import('@/pages/Teardown'))
const Events = lazy(() => import('@/pages/Events'))
const ApiTokens = lazy(() => import('@/pages/ApiTokens'))
const Webhooks = lazy(() => import('@/pages/Webhooks'))
const Features = lazy(() => import('@/pages/Features'))
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
        <Route path="/power" element={<Power />} />
        <Route path="/problems" element={<Problems />} />
        <Route path="/setup" element={<Setup />} />
        <Route path="/stats" element={<Stats />} />
        <Route path="/traffic" element={<Traffic />} />
        <Route path="/dns" element={<Dns />} />
        <Route path="/games" element={<Games />} />
        <Route path="/logs" element={<Logs />} />
        <Route path="/templates" element={<Templates />} />
        <Route path="/replay" element={<Replay />} />
        <Route path="/report" element={<Report />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/tournament" element={<Tournament />} />
        <Route path="/handover" element={<Handover />} />
        <Route path="/planner" element={<Planner />} />
        <Route path="/preflight" element={<Preflight />} />
        <Route path="/gear" element={<Gear />} />
        <Route path="/teardown" element={<Teardown />} />
        <Route path="/events" element={<Events />} />
        <Route path="/settings/features" element={<Features />} />
        <Route path="/settings/api" element={<ApiTokens />} />
        <Route path="/settings/webhooks" element={<Webhooks />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  )
}
