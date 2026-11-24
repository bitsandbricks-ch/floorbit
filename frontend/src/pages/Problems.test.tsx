import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ProblemList } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Problems from './Problems'

afterEach(() => vi.unstubAllGlobals())

/** The problem rows, without the header. */
const bodyRows = () => screen.queryAllByRole('row').filter((r) => r.closest('tbody'))

const now = Date.now() / 1000
const list = (over: Partial<ProblemList> = {}): ProblemList => ({
  problems: [
    { id: 'switch:s1', kind: 'switch', level: 'down', title: 'sw-c-02 is offline', where: 'sw-c-02', since: now - 300, link: '/plan?switch=sw-c-02', switch_id: 's1', muted: null },
    { id: 'power:c1', kind: 'power', level: 'warn', title: 'Circuit B row 2 getting close (86.9 %)', where: 'Feeds 12 seats', since: now, link: '/power' },
    { id: 'switch:s2', kind: 'switch', level: 'down', title: 'sw-d-01 is offline', where: 'sw-d-01', since: now - 60, link: '/plan?switch=sw-d-01', switch_id: 's2',
      muted: { until: now + 3600, by: 'kim', reason: 'Recabling' } },
  ],
  counts: { down: 1, warn: 1, muted: 1 },
  mutes: [{ switch_id: 's2', name: 'sw-d-01', until: now + 3600, at: now, by: 'kim', reason: 'Recabling' }],
  quiet_hours: false, checked_at: now, can_mute: true, ...over,
})
const me = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: ['incidents.work'] } }

describe('Problems', () => {
  it('lists what is wrong, worst first, with mutes', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list() }).fn)
    renderWithApp(<Problems />)
    const sw = await screen.findByRole('row', { name: 'sw-c-02 is offline' })
    expect(within(sw).getByText('Switch')).toBeInTheDocument()
    // The counts are cards now (issue #103): label, then the number.
    const card = (label: string) => screen.getByText(label, { selector: 'dt > span' }).closest('dl')
    expect(card('Down')).toHaveTextContent('Down1')
    expect(card('Muted')).toHaveTextContent('Muted1')
    // Down and warn show in a background tab; the muted switch doesn't (issue #214).
    expect(document.title).toBe('(2) Problems · Floorbit')
    const muted = screen.getByRole('row', { name: 'sw-d-01 is offline' })
    expect(within(muted).queryByRole('button', { name: 'Mute' })).not.toBeInTheDocument()
    expect(within(muted).getByText(/Recabling/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Muted alerts' })).toBeInTheDocument()
    // The muted switch opens on the floor plan, in its hall (issue #212).
    expect(screen.getByRole('link', { name: 'sw-d-01' })).toHaveAttribute('href', '/plan?switch=sw-d-01')
  })

  it('counts the seats a down switch cuts off, and points a switch behind it at the cause', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list({
      problems: [
        { id: 'switch:a1', kind: 'switch', level: 'down', title: 'sw-a-01 is offline', where: 'sw-a-01', since: now, link: '/plan?switch=sw-a-01',
          switch_id: 'a1', seats: ['A-1', 'A-2', 'A-3'], behind: ['sw-a-02'] },
        { id: 'switch:a2', kind: 'switch', level: 'down', title: 'sw-a-02 is offline', where: 'sw-a-02', since: now, link: '/plan?switch=sw-a-02',
          switch_id: 'a2', seats: ['A-3'], behind: [], cause: 'sw-a-01' },
      ],
    }) }).fn)
    renderWithApp(<Problems />)
    const first = await screen.findByRole('row', { name: 'sw-a-01 is offline' })
    expect(within(first).getByText('3 seats affected · 1 switch behind it')).toBeInTheDocument()
    fireEvent.click(within(first).getByRole('button', { name: 'Show the seats' }))
    expect(within(first).getByText('A-1, A-2, A-3')).toBeInTheDocument()
    const second = screen.getByRole('row', { name: 'sw-a-02 is offline' })
    expect(within(second).getByText('Behind sw-a-01, which is down: start there')).toBeInTheDocument()
  })

  it('lists seat and port trouble with the rest, worst first, with a Seats filter (issue #1204)', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list({
      counts: { down: 1, warn: 1, muted: 1, seats: 2 },
      attention: [
        { id: 'incident:i1', kind: 'incident', level: 'warn', title: 'No internet at the seat',
          where: 'Seat B-4, on the incident board', since: now, link: '/incidents?q=seat%3AB-4', seat: 'B-4' },
        { id: 'attention:checkin:s1:Gi1/0/12', kind: 'checkin', level: 'warn', title: 'Seat A-12 is online without a check-in',
          where: 'sw-a-01 Gi1/0/12 (seat A-12)', since: now, link: '/plan?seat=A-12', switch_id: 's1', seat: 'A-12' },
        { id: 'attention:flapping:s1:Gi1/0/9', kind: 'flapping', level: 'warn', title: 'Port flapping: 4 link changes in 10 minutes',
          where: 'sw-a-01 Gi1/0/9', since: now - 120, link: '/plan?switch=sw-a-01', switch_id: 's1' },
      ],
    }) }).fn)
    renderWithApp(<Problems />)
    await screen.findByRole('row', { name: 'No internet at the seat' })
    const names = () => bodyRows().map((a) => a.getAttribute('aria-label'))
    // Worst first (issue #883): down, then to look at, longest standing first, muted last.
    expect(names()).toEqual(['sw-c-02 is offline', 'Port flapping: 4 link changes in 10 minutes', 'Circuit B row 2 getting close (86.9 %)',
      'No internet at the seat', 'Seat A-12 is online without a check-in', 'sw-d-01 is offline'])
    const card = (label: string) => screen.getByText(label, { selector: 'dt > span' }).closest('dl')
    expect(card('Seats with trouble')).toHaveTextContent('Seats with trouble2')
    const incident = screen.getByRole('row', { name: 'No internet at the seat' })
    expect(within(incident).getByText('Incident')).toBeInTheDocument()
    expect(within(incident).getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/incidents?q=seat%3AB-4')
    expect(within(incident).queryByRole('button', { name: 'Mute' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: /Seats/ }))
    await vi.waitFor(() => expect(names()).toEqual(['No internet at the seat', 'Seat A-12 is online without a check-in']))
  })

  it('pages a long list, the page in the address (issue #1204)', async () => {
    const many = Array.from({ length: 30 }, (_, i) => ({
      id: `attention:errors:s1:Gi1/0/${i + 1}`, kind: 'errors' as const, level: 'warn' as const, title: `Errors rising on Gi1/0/${i + 1}`,
      where: `sw-a-01 Gi1/0/${i + 1}`, since: now - i, link: '/plan?switch=sw-a-01', switch_id: 's1' }))
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list({ attention: many }) }).fn)
    renderWithApp(<Problems />)
    await screen.findByRole('row', { name: 'sw-c-02 is offline' })
    expect(bodyRows()).toHaveLength(25)
    expect(screen.getByText('33 problems')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: '2' }).at(-1)!)
    await vi.waitFor(() => expect(bodyRows()).toHaveLength(8))
    expect(screen.getByRole('row', { name: 'Errors rising on Gi1/0/1' })).toBeInTheDocument()
    expect(screen.getByRole('row', { name: 'sw-d-01 is offline' })).toBeInTheDocument()
  })

  it('mutes a switch for the chosen time', async () => {
    const fake = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list(), 'POST /api/alerts/mutes': { status: 201, body: {} } })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Problems />)
    const sw = await screen.findByRole('row', { name: 'sw-c-02 is offline' })
    fireEvent.click(within(sw).getByRole('button', { name: 'Mute' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText(/Why/), { target: { value: 'Swapping the PSU' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Mute' }))
    await vi.waitFor(() => expect(fake.calls.find((c) => c.path === '/api/alerts/mutes')?.body)
      .toEqual({ switch_id: 's1', minutes: 60, reason: 'Swapping the PSU' }))
  })

  it('makes a running mute last half an hour longer', async () => {
    const fake = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list(), 'PATCH /api/alerts/mutes/s2': { body: {} } })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Problems />)
    fireEvent.click(await screen.findByRole('button', { name: 'Mute sw-d-01 30 minutes longer' }))
    await vi.waitFor(() => expect(fake.calls.find((c) => c.method === 'PATCH')?.body).toEqual({ minutes: 30 }))
  })

  it('shows one kind at a time, with counts, and keeps it in the link', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list() }).fn)
    renderWithApp(<Problems />, '/problems?kind=power')
    expect(await screen.findByRole('row', { name: /Circuit B row 2/ })).toBeInTheDocument()
    expect(screen.queryByRole('row', { name: 'sw-c-02 is offline' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: /^Switch/ }))
    await vi.waitFor(() => expect(bodyRows()).toHaveLength(2))
    expect(screen.queryByRole('row', { name: /Circuit B row 2/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: /^All/ }))
    await vi.waitFor(() => expect(bodyRows()).toHaveLength(3))
  })

  it('makes an incident from an offline switch, or links the open one', async () => {
    const problems = list().problems.map((p) => p.id === 'switch:s1' ? { ...p, name: 'sw-c-02', incident: null }
      : p.id === 'switch:s2' ? { ...p, name: 'sw-d-01', incident: 'abc123' } : p)
    const fake = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list({ problems, can_report: true }),
      'POST /api/incidents': { status: 201, body: {} } })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Problems />)
    const open = await screen.findByRole('row', { name: 'sw-d-01 is offline' })
    expect(within(open).getByRole('link', { name: 'Incident open' })).toHaveAttribute('href', '/incidents/abc123')
    const down = screen.getByRole('row', { name: 'sw-c-02 is offline' })
    fireEvent.click(within(down).getByRole('button', { name: 'Make an incident' }))
    await vi.waitFor(() => expect(fake.calls.find((c) => c.method === 'POST' && c.path === '/api/incidents')?.body)
      .toEqual({ switch_id: 's1', title: 'sw-c-02 is offline', from_problem: 'switch:s1' }))
  })

  it('says when a mute is about to end, and only then', async () => {
    const mutes = [
      { switch_id: 's2', name: 'sw-d-01', until: now + 240, at: now, by: 'kim', reason: '' },
      { switch_id: 's3', name: 'sw-d-02', until: now + 3600, at: now, by: 'kim', reason: '' },
    ]
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list({ mutes }) }).fn)
    renderWithApp(<Problems />)
    expect(await screen.findByText('ends in 4 minutes')).toBeInTheDocument()
    expect(screen.getAllByText(/^ends in/)).toHaveLength(1)
  })

  it('mutes a service on the health wall, and lists it with the muted switches', async () => {
    const service = { id: 'health:demo:game-1', kind: 'health' as const, level: 'down' as const, title: 'Game server 1: down', where: 'Not answering',
      since: now, link: '/services', mute_id: 'health:demo:game-1', name: 'Game server 1', muted: null }
    const fake = fakeFetch({
      'GET /api/auth/me': me,
      'GET /api/problems': list({ problems: [service], mutes: [{ switch_id: 'health:demo:dns', kind: 'health', name: 'DNS', until: now + 600, at: now, by: 'kim', reason: '' }] }),
      'POST /api/alerts/mutes': { status: 201, body: {} },
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Problems />)
    const row = await screen.findByRole('row', { name: 'Game server 1: down' })
    expect(screen.getByRole('link', { name: 'DNS' })).toHaveAttribute('href', '/services')
    fireEvent.click(within(row).getByRole('button', { name: 'Mute' }))
    const dialog = await screen.findByRole('dialog', { name: 'Mute alerts for Game server 1' })
    expect(within(dialog).getByText(/this service going down/)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Mute' }))
    await vi.waitFor(() => expect(fake.calls.find((c) => c.path === '/api/alerts/mutes')?.body)
      .toEqual({ service_id: 'demo:game-1', minutes: 60, reason: '' }))
  })

  it('offers the swap page for an offline switch to those who may change the inventory (issue #1060)', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list() }).fn)
    const view = renderWithApp(<Problems />)
    await screen.findByText('sw-c-02 is offline')
    expect(screen.queryByRole('link', { name: 'Swap' })).not.toBeInTheDocument()
    view.unmount()
    const lead = { enabled: true, user: { ...me.user, role: 'lead', permissions: ['incidents.work', 'floorplan.edit'] } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/problems': list() }).fn)
    renderWithApp(<Problems />)
    await screen.findByText('sw-c-02 is offline')
    await waitFor(() => expect(screen.getAllByRole('link', { name: 'Swap' })[0]).toHaveAttribute('href', '/switch-swap/s1'))
  })

  it('mutes a Wi-Fi access point by its name', async () => {
    const ap = { id: 'wifi:down:ap-stage', kind: 'wifi' as const, level: 'down' as const, title: 'ap-stage is down', where: 'wlc-01',
      since: now, link: '/dashboards/view/network', mute_id: 'wifi:ap-stage', name: 'ap-stage', muted: null }
    const fake = fakeFetch({
      'GET /api/auth/me': me,
      'GET /api/problems': list({ problems: [ap], mutes: [{ switch_id: 'wifi:ap-crew', kind: 'wifi', name: 'ap-crew', until: now + 600, at: now, by: 'kim', reason: '' }] }),
      'POST /api/alerts/mutes': { status: 201, body: {} },
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Problems />)
    const row = await screen.findByRole('row', { name: 'ap-stage is down' })
    expect(within(row).getByText('Wi-Fi')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'ap-crew' })).toHaveAttribute('href', '/dashboards/view/network')
    fireEvent.click(within(row).getByRole('button', { name: 'Mute' }))
    const dialog = await screen.findByRole('dialog', { name: 'Mute alerts for ap-stage' })
    expect(within(dialog).getByText(/in the Wi-Fi view/)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Mute' }))
    await vi.waitFor(() => expect(fake.calls.find((c) => c.path === '/api/alerts/mutes')?.body)
      .toEqual({ ap: 'ap-stage', minutes: 60, reason: '' }))
  })

  it('says when all is well', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list({ problems: [], mutes: [], counts: { down: 0, warn: 0, muted: 0 } }) }).fn)
    renderWithApp(<Problems />)
    expect(await screen.findByText('Nothing is wrong right now.')).toBeInTheDocument()
    expect(document.title).toBe('Problems · Floorbit')
  })

  it('copies what is shown as text for the crew chat', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list() }).fn)
    renderWithApp(<Problems />)
    fireEvent.click(await screen.findByRole('button', { name: 'Copy list' }))
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
    const text: string = writeText.mock.calls[0][0]
    const lines = text.split('\n')
    expect(lines[0]).toMatch(/^Problems [^:]+:\d\d[^:]*: 1 down · 1 to look at · 1 muted$/)
    expect(lines[1]).toBe('- [Switch] sw-c-02 is offline (sw-c-02, started 5 minutes ago)')
    expect(lines[2]).toBe('- [Power] Circuit B row 2 getting close (86.9 %) (Feeds 12 seats, started now)')
    expect(lines[3]).toMatch(/^- \[Switch\] sw-d-01 is offline \(sw-d-01, started 1 minute ago, Muted until .+ by kim\)$/)
    expect(text).toContain('Muted alerts:\n- sw-d-01, Muted until')
    expect(text).toContain('(Recabling)')
  })

  it('clears a LibreNMS alert whose recovery got lost', async () => {
    const alert = { id: 'librenms:abc', kind: 'librenms' as const, level: 'down' as const, title: 'Port down on sw-a-01',
      where: 'sw-a-01: Gi1/0/5', since: now, link: '/plan?switch=sw-a-01', switch_id: 's1', clear_id: 'abc' }
    const api = fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list({ problems: [alert] }),
      'DELETE /api/alerts/librenms/abc': { ok: true } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<Problems />)
    const row = await screen.findByRole('row', { name: 'Port down on sw-a-01' })
    expect(within(row).getByText('LibreNMS')).toBeInTheDocument()
    expect(within(row).queryByRole('button', { name: 'Mute' })).not.toBeInTheDocument()
    fireEvent.click(within(row).getByRole('button', { name: 'Clear' }))
    await vi.waitFor(() => expect(api.calls.some((c) => c.method === 'DELETE' && c.path === '/api/alerts/librenms/abc')).toBe(true))
  })

  it('filters by severity and muted, and groups by switch, all in the address (issue #883)', async () => {
    const attention = [
      { id: 'attention:errors:s1:Gi1/0/9', kind: 'errors' as const, level: 'warn' as const, title: 'Errors rising on Gi1/0/9',
        where: 'sw-c-02 Gi1/0/9', since: now, link: '/plan?switch=sw-c-02', switch_id: 's1', device: 'sw-c-02' },
    ]
    const problems = list().problems.map((p) => ({ ...p, device: p.kind === 'switch' ? p.where : null }))
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': me, 'GET /api/problems': list({ problems, attention }) }).fn)
    renderWithApp(<Problems />, '/problems?level=down&muted=hide')
    await screen.findByRole('row', { name: 'sw-c-02 is offline' })
    expect(bodyRows().map((r) => r.getAttribute('aria-label'))).toEqual(['sw-c-02 is offline'])
    fireEvent.click(screen.getByRole('checkbox', { name: 'Hide muted' }))
    await vi.waitFor(() => expect(bodyRows()).toHaveLength(2))
    const grouped = renderWithApp(<Problems />, '/problems?group=device')
    const sw = await within(grouped.container).findByRole('region', { name: 'sw-c-02' })
    expect(within(sw).getAllByRole('row').filter((r) => r.closest('tbody')).map((r) => r.getAttribute('aria-label')))
      .toEqual(['sw-c-02 is offline', 'Errors rising on Gi1/0/9'])
    const loose = within(grouped.container).getByRole('region', { name: 'Not on a switch' })
    expect(within(loose).getByRole('row', { name: /Circuit B row 2/ })).toBeInTheDocument()
  })
})
