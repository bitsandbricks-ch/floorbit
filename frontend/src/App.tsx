import { lazy, Suspense } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import { AppShell } from '@/components/Layout'
import { PageError } from '@/components/PageError'
import { readServerPage } from '@/lib/serverPage'

// Each page is its own chunk. Flask sends only these paths to the React app (floorbit/spa.py).
const Dashboards = lazy(() => import('@/pages/Dashboards'))
const Overview = lazy(() => import('@/pages/Overview'))
const DashboardView = lazy(() => import('@/pages/DashboardView'))
const Widgets = lazy(() => import('@/pages/widgets/Widgets'))
const DashboardScreen = lazy(() => import('@/pages/DashboardScreen'))
const Plugins = lazy(() => import('@/pages/Plugins'))
const PluginSettings = lazy(() => import('@/pages/PluginSettings'))
const PluginPage = lazy(() => import('@/pages/PluginPage'))
const Inventory = lazy(() => import('@/pages/Inventory'))
const DevicePage = lazy(() => import('@/pages/inventory/DevicePage'))
const ScopePage = lazy(() => import('@/pages/inventory/ScopePage'))
const EntryPage = lazy(() => import('@/pages/inventory/EntryPage'))
const SeatMapping = lazy(() => import('@/pages/SeatMapping'))
const Incidents = lazy(() => import('@/pages/Incidents'))
const HelpdeskQr = lazy(() => import('@/pages/HelpdeskQr'))
const Security = lazy(() => import('@/pages/Security'))
const Power = lazy(() => import('@/pages/Power'))
const BoardPage = lazy(() => import('@/pages/power/BoardPage'))
const CircuitPage = lazy(() => import('@/pages/power/CircuitPage'))
const Problems = lazy(() => import('@/pages/Problems'))
const Setup = lazy(() => import('@/pages/Setup'))
const Topology = lazy(() => import('@/pages/Topology'))
const Firewalls = lazy(() => import('@/pages/Firewalls'))
const Services = lazy(() => import('@/pages/Services'))
const Logs = lazy(() => import('@/pages/Logs'))
const Commands = lazy(() => import('@/pages/Commands'))
const TerminalPage = lazy(() => import('@/pages/Terminal'))
const Configs = lazy(() => import('@/pages/Configs'))
const Templates = lazy(() => import('@/pages/Templates'))
const Replay = lazy(() => import('@/pages/Replay'))
const Report = lazy(() => import('@/pages/Report'))
const Jobs = lazy(() => import('@/pages/Jobs'))
const Handover = lazy(() => import('@/pages/Handover'))
const Cables = lazy(() => import('@/pages/Cables'))
const WalkRow = lazy(() => import('@/pages/WalkRow'))
const CablePage = lazy(() => import('@/pages/cables/CablePage'))
const SeatWalk = lazy(() => import('@/pages/SeatWalk'))
const SwitchAreas = lazy(() => import('@/pages/SwitchAreas'))
const SwitchSwap = lazy(() => import('@/pages/SwitchSwap'))
const Telemetry = lazy(() => import('@/pages/Telemetry'))
const Endpoints = lazy(() => import('@/pages/Endpoints'))
const ViewPage = lazy(() => import('@/pages/monitoring/ViewPage'))
const Timeline = lazy(() => import('@/pages/Timeline'))
const NetworkStatus = lazy(() => import('@/pages/NetworkStatus'))
const Schedule = lazy(() => import('@/pages/Schedule'))
const FloorPlan = lazy(() => import('@/pages/FloorPlan'))
const Checkins = lazy(() => import('@/pages/Checkins'))
const Events = lazy(() => import('@/pages/Events'))
const Login = lazy(() => import('@/pages/Login'))
const Checkin = lazy(() => import('@/pages/Checkin'))
const Agents = lazy(() => import('@/pages/Agents'))
const AgentDetail = lazy(() => import('@/pages/AgentDetail'))
const Settings = lazy(() => import('@/pages/Settings'))
const PublicStatus = lazy(() => import('@/pages/public/PublicStatus'))
const Forbidden = lazy(() => import('@/pages/Forbidden'))
const SeatHelp = lazy(() => import('@/pages/public/SeatHelp'))
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
      <Suspense fallback={null}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/checkin" element={<Checkin />} />
          <Route path="/status" element={<PublicStatus />} />
          <Route path="/help/:seat" element={<SeatHelp />} />
          {/* A dashboard on a big screen: the page alone, no sidebar. */}
          <Route path="/dashboards/:id" element={<DashboardScreen />} />
          <Route element={<AppShell />}>
            <Route path="/overview" element={<Overview />} />
            <Route path="/dashboards" element={<Dashboards />} />
            <Route path="/dashboards/view/:id" element={<DashboardView />} />
            <Route path="/widgets" element={<Widgets />} />
            <Route path="/settings/plugins" element={<Plugins />} />
            <Route path="/settings/plugins/:id" element={<PluginSettings />} />
            <Route path="/plugins/:plugin/:page" element={<PluginPage />} />
            <Route path="/inventory" element={<Inventory />} />
            <Route path="/inventory/devices/:id" element={<DevicePage />} />
            <Route path="/inventory/groups/:id" element={<ScopePage kind="group" />} />
            <Route path="/inventory/tags/:id" element={<ScopePage kind="tag" />} />
            <Route path="/inventory/defaults" element={<ScopePage kind="defaults" />} />
            <Route path="/inventory/entries/:type/:id" element={<EntryPage />} />
            <Route path="/seat-mapping" element={<SeatMapping />} />
            <Route path="/incidents" element={<Incidents />} />
            <Route path="/incidents/qr" element={<HelpdeskQr />} />
            <Route path="/security" element={<Security />} />
            <Route path="/power" element={<Power />} />
            <Route path="/power/boards/:id" element={<BoardPage />} />
            <Route path="/power/circuits/:id" element={<CircuitPage />} />
            <Route path="/problems" element={<Problems />} />
            <Route path="/setup" element={<Setup />} />
            <Route path="/topology" element={<Topology />} />
            <Route path="/firewalls" element={<Firewalls />} />
            <Route path="/services" element={<Services />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/commands" element={<Commands />} />
            <Route path="/terminal" element={<TerminalPage />} />
            <Route path="/configs" element={<Configs />} />
            <Route path="/templates" element={<Templates />} />
            <Route path="/replay" element={<Replay />} />
            <Route path="/report" element={<Report />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/handover" element={<Handover />} />
            <Route path="/cables" element={<Cables />} />
            <Route path="/cables/walk" element={<WalkRow />} />
            <Route path="/cables/:id" element={<CablePage />} />
            <Route path="/seat-walk" element={<SeatWalk />} />
            <Route path="/switch-areas" element={<SwitchAreas />} />
            <Route path="/switch-swap/:id" element={<SwitchSwap />} />
            <Route path="/timeline" element={<Timeline />} />
            <Route path="/network-status" element={<NetworkStatus />} />
            <Route path="/schedule" element={<Schedule />} />
            <Route path="/plan" element={<FloorPlan />} />
            <Route path="/checkins" element={<Checkins />} />
            <Route path="/events" element={<Events />} />
            <Route path="/settings/:section?" element={<Settings />} />
            <Route path="/settings/agents" element={<Agents />} />
            <Route path="/settings/agents/:id" element={<AgentDetail />} />
            <Route path="/telemetry" element={<Telemetry />} />
            <Route path="/endpoints" element={<Endpoints />} />
            <Route path="/wifi" element={<ViewPage key="wifi" view="wifi" />} />
            <Route path="/dns" element={<ViewPage key="dns" view="dns" />} />
            <Route path="/lancache" element={<ViewPage key="lancache" view="lancache" />} />
            <Route path="/traffic" element={<ViewPage key="traffic" view="traffic" />} />
            <Route path="/games" element={<ViewPage key="games" view="games" />} />
            <Route path="/stats" element={<ViewPage key="stats" view="stats" />} />
            <Route path="/speedtests" element={<ViewPage key="speedtests" view="speedtests" />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Suspense>
    </PageError>
  )
}
