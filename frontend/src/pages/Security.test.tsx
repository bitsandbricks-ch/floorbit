import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Finding, SecurityList } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Security from './Security'

afterEach(() => vi.unstubAllGlobals())

const now = Date.now() / 1000
const finding: Finding = {
  id: 'demo:arp-1', plugin: 'demo', plugin_name: 'Demo data', kind: 'arp-spoof', severity: 'high',
  title: '192.0.2.42 is answered by two MACs', detail: 'Someone may be intercepting traffic.',
  switch: 'sw-b-01', port: 'Gi1/0/4', seat: 'B-4', mac: '02:00:00:00:00:1b', ip: '192.0.2.42',
  evidence: ['02:00:00:00:00:1b on Gi1/0/4'], first_seen: now - 300, last_seen: now, ack: null,
}
const list = (over: Partial<SecurityList> = {}): SecurityList => ({
  findings: [finding], cleared: [], shut_ports: [], last_poll: now, interval: 60, plugins: 1,
  can_act: true, needs_login: true, ...over,
})
const me = { enabled: true, user: { username: 'sam', display_name: 'Sam', role: 'tech', permissions: ['seats.view', 'ports.act'] } }

describe('Security findings', () => {
  it('shows each finding with where it is', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/security': list() }).fn)
    renderWithApp(<Security />)
    const card = await screen.findByRole('article', { name: finding.title })
    expect(within(card).getByText('High')).toBeInTheDocument()
    expect(within(card).getByText('ARP spoofing')).toBeInTheDocument()
    expect(within(card).getByText('Seat B-4 (sw-b-01 · Gi1/0/4)')).toBeInTheDocument()
    expect(within(card).getByText('02:00:00:00:00:1b on Gi1/0/4')).toBeInTheDocument()
  })

  it('shuts a finding’s port with the tech’s own login, naming only the finding', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': me,
      'GET /api/security': list(),
      'POST /api/ports/shutdown': { ok: true, message: 'Gi1/0/4 on sw-b-01 is shut.' },
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Security />)
    fireEvent.click(await screen.findByRole('button', { name: 'Shut port' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText(/Your switch username/), { target: { value: 'kim' } })
    fireEvent.change(within(dialog).getByLabelText(/Your switch password/), { target: { value: 'secret' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Shut port' }))
    expect(await screen.findByText('Gi1/0/4 on sw-b-01 is shut.')).toBeInTheDocument()
    const call = fake.calls.find((c) => c.path === '/api/ports/shutdown')
    expect(call?.body).toEqual({ finding: 'demo:arp-1', username: 'kim', password: 'secret' })
  })

  it('hides the shutdown without port actions and says when nothing is watching', async () => {
    vi.stubGlobal('fetch', fakeFetch({
      'GET /api/auth/me': me,
      'GET /api/security': list({ findings: [], plugins: 0, can_act: false }),
    }).fn)
    renderWithApp(<Security />)
    expect(await screen.findByText(/No security plugin is on yet/)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Shut port' })).not.toBeInTheDocument())
  })
})
