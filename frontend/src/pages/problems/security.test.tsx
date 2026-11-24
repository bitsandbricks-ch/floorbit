import { fireEvent, screen, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ProblemDetail, SecurityList } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import ProblemPage from '../ProblemPage'
import { ShutPorts } from './ShutPorts'

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: ['incidents.work', 'seats.view', 'ports.act'] } }
const id = 'security:demo:arp-1'
const finding = {
  id: 'demo:arp-1', kind: 'arp-spoof', severity: 'high', detail: 'Two MACs answer for one IP.', switch: 'sw-b-01', port: 'Gi1/0/4',
  seat: 'B-4', mac: '02:00:00:00:00:1b', ip: '192.0.2.42', evidence: ['02:00:00:00:00:1b on Gi1/0/4', '02:00:00:00:00:2c on Gi1/0/9'],
  plugin: 'demo', plugin_name: 'Demo data', first_seen: now - 300, last_seen: now, uplink: null,
} as const
const detail = (over: Partial<ProblemDetail> = {}): ProblemDetail => ({
  problem: { id, kind: 'security', level: 'down', title: '192.0.2.42 is answered by two MACs', where: 'Seat B-4 (sw-b-01 Gi1/0/4)',
    since: now - 300, link: '', seat: 'B-4', device: 'sw-b-01', incident: null },
  device: null, can_mute: true, can_report: true, may_see_people: true,
  finding: { ...finding, evidence: [...finding.evidence] }, can_shut: true, needs_login: false, ...over,
})
const open = (routes: Record<string, unknown>) => {
  const api = fakeFetch({ 'GET /api/auth/me': me, ...routes })
  vi.stubGlobal('fetch', api.fn)
  renderWithApp(<Routes><Route path="/problems/:id" element={<ProblemPage />} /></Routes>, `/problems/${encodeURIComponent(id)}`)
  return api
}
const path = `GET /api/problems/${encodeURIComponent(id)}`

describe('a security finding is a problem (issue #885)', () => {
  it('shows what the plugin saw, and shuts the finding\'s port', async () => {
    const api = open({ [path]: detail(), 'POST /api/ports/shutdown': { message: 'Shut sw-b-01 Gi1/0/4.' } })
    expect(await screen.findByText('What the security plugin saw')).toBeInTheDocument()
    expect(screen.getByText('02:00:00:00:00:2c on Gi1/0/9')).toBeInTheDocument()
    expect(screen.getByText('Two MACs answer for one IP.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Make an incident' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: "I'm on it" })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Shut port' }))
    fireEvent.change(await screen.findByLabelText('Why (shown in the list of shut ports)'), { target: { value: 'ARP spoofing' } })
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Shut port' }))
    await vi.waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({ finding: 'demo:arp-1', reason: 'ARP spoofing' }))
    expect(await screen.findByText('Shut sw-b-01 Gi1/0/4.')).toBeInTheDocument()
  })

  it('offers the switch terminal instead on an uplink', async () => {
    open({ [path]: detail({ finding: { ...finding, evidence: [], uplink: 'topology' } }) })
    expect(await screen.findByRole('link', { name: 'Open the switch' })).toHaveAttribute('href', '/terminal?switch=sw-b-01')
    expect(screen.queryByRole('button', { name: 'Shut port' })).not.toBeInTheDocument()
  })
})

const list = (over: Partial<SecurityList> = {}): SecurityList => ({
  findings: [], cleared: [], last_poll: now, interval: 60, plugins: 1, can_act: true, needs_login: false,
  shut_ports: [{ switch: 'sw-b-01', port: 'Gi1/0/4', seat: 'B-4', by: 'kim', at: now - 60, reason: 'ARP spoofing' }], ...over,
})

describe('ports Floorbit shut, under the problems', () => {
  it('lists them and turns one on again', async () => {
    const api = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/security': list(), 'POST /api/ports/enable': { message: 'Turned on.' } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<ShutPorts always={false} />)
    expect(await screen.findByText('ARP spoofing')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'Turn port on' })[0])
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Turn port on' }))
    await vi.waitFor(() => expect(api.calls.find((c) => c.method === 'POST')?.body).toEqual({ switch: 'sw-b-01', port: 'Gi1/0/4' }))
  })

  it('stays out of the way while no port is shut, unless security is filtered', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/security': list({ shut_ports: [] }) }).fn)
    const { unmount } = renderWithApp(<ShutPorts always={false} />)
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText('Ports Floorbit shut')).not.toBeInTheDocument()
    unmount()
    renderWithApp(<ShutPorts always />)
    expect(await screen.findByText('No port is shut.')).toBeInTheDocument()
  })
})
