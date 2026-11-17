import { lazy, Suspense } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import { AppShell } from '@/components/Layout'
import { PageError } from '@/components/PageError'

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
const GameServers = lazy(() => import('@/pages/GameServers'))
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
const Tournament = lazy(() => import('@/pages/Tournament'))
const Handover = lazy(() => import('@/pages/Handover'))
const Preflight = lazy(() => import('@/pages/Preflight'))
const Gear = lazy(() => import('@/pages/Gear'))
const Cables = lazy(() => import('@/pages/Cables'))
const WalkRow = lazy(() => import('@/pages/WalkRow'))
const SwitchLogins = lazy(() => import('@/pages/SwitchLogins'))
const Wifi = lazy(() => import('@/pages/Wifi'))
const Timeline = lazy(() => import('@/pages/Timeline'))
const NetworkStatus = lazy(() => import('@/pages/NetworkStatus'))
const Runbooks = lazy(() => import('@/pages/Runbooks'))
const Schedule = lazy(() => import('@/pages/Schedule'))
const Brackets = lazy(() => import('@/pages/Brackets'))
const FloorPlan = lazy(() => import('@/pages/FloorPlan'))
const Speedtests = lazy(() => import('@/pages/Speedtests'))
const Checkins = lazy(() => import('@/pages/Checkins'))
const Events = lazy(() => import('@/pages/Events'))
const ApiTokens = lazy(() => import('@/pages/ApiTokens'))
const Audit = lazy(() => import('@/pages/Audit'))
const Users = lazy(() => import('@/pages/Users'))
const Login = lazy(() => import('@/pages/Login'))
const Checkin = lazy(() => import('@/pages/Checkin'))
const Agents = lazy(() => import('@/pages/Agents'))
const Webhooks = lazy(() => import('@/pages/Webhooks'))
const Features = lazy(() => import('@/pages/Features'))
const Settings = lazy(() => import('@/pages/Settings'))
const NotFound = lazy(() => import('@/pages/NotFound'))

export default function App() {
  const { pathname } = useLocation()
  return (
    // Outside the shell too (sign-in, check-in): an error there shows a way out, not a blank window.
    <PageError resetKey={pathname}>
      <Suspense fallback={null}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/checkin" element={<Checkin />} />
          <Route element={<AppShell />}>
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
            <Route path="/game-servers" element={<GameServers />} />
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
            <Route path="/tournament" element={<Tournament />} />
            <Route path="/handover" element={<Handover />} />
            <Route path="/preflight" element={<Preflight />} />
            <Route path="/gear" element={<Gear />} />
            <Route path="/cables" element={<Cables />} />
            <Route path="/cables/walk" element={<WalkRow />} />
            <Route path="/wifi" element={<Wifi />} />
            <Route path="/timeline" element={<Timeline />} />
            <Route path="/network-status" element={<NetworkStatus />} />
            <Route path="/runbooks" element={<Runbooks />} />
            <Route path="/schedule" element={<Schedule />} />
            <Route path="/tournament/brackets" element={<Brackets />} />
            <Route path="/plan" element={<FloorPlan />} />
            <Route path="/checkins" element={<Checkins />} />
            <Route path="/speedtests" element={<Speedtests />} />
            <Route path="/events" element={<Events />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/settings/features" element={<Features />} />
            <Route path="/settings/api" element={<ApiTokens />} />
            <Route path="/settings/audit" element={<Audit />} />
            <Route path="/settings/users" element={<Users />} />
            <Route path="/settings/agents" element={<Agents />} />
            <Route path="/settings/webhooks" element={<Webhooks />} />
            <Route path="/settings/credentials" element={<SwitchLogins />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Suspense>
    </PageError>
  )
}
