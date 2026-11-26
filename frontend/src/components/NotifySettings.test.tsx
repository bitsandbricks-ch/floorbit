import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { qk } from '@/api/keys'
import { CrewNotify } from '@/notify/CrewNotify'
import { crewNotify, migrate, setWatchedSeats, watchedSeats } from '@/notify/crewNotify'
import { fakeFetch, renderWithApp } from '@/test/render'
import { NotifySettings } from './NotifySettings'

type Shown = { title: string; body: string; tag: string }

class FakeSource {
  static last: FakeSource | null = null
  handlers: Record<string, (e: { data: string }) => void> = {}
  readyState = 1
  constructor() { FakeSource.last = this }
  addEventListener(type: string, fn: (e: { data: string }) => void) { this.handlers[type] = fn }
  close() {}
  emit(type: string, data: unknown) { this.handlers[type]?.({ data: JSON.stringify({ type, data }) }) }
}

let shown: Shown[] = []

beforeEach(() => {
  shown = []
  const Note = vi.fn(function (this: object, title: string, opts: { body: string; tag: string }) { shown.push({ title, ...opts }) })
  vi.stubGlobal('Notification', Object.assign(Note, { permission: 'granted', requestPermission: async () => 'granted' }))
  vi.stubGlobal('EventSource', FakeSource)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  localStorage.clear()
  FakeSource.last = null
})

/** CrewNotify listening, signed in as tia; resolves once it knows who "me" is. */
async function listen(mutes: { switch_id: string }[] = []) {
  vi.stubGlobal('fetch', fakeFetch({
    'GET /api/auth/me': { enabled: true, user: { username: 'tia', permissions: [] } },
    'GET /api/problems': { mutes },
    'GET /api/incidents': { incidents: [{ id: 'i1', seat: 'D-6', title: 'No link' }] },
  }).fn)
  const { client } = renderWithApp(<CrewNotify />)
  await waitFor(() => expect(client.getQueryData(qk.me)).toBeTruthy())
  await waitFor(() => expect(FakeSource.last?.handlers['seats.changed']).toBeTruthy())
  return FakeSource.last!
}

describe('CrewNotify', () => {
  it('opens no stream while notifications are off', async () => {
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    renderWithApp(<CrewNotify />)
    await new Promise((r) => setTimeout(r, 20))
    expect(FakeSource.last).toBeNull()
  })

  it('shows a job for me, a new incident and a switch going down', async () => {
    await crewNotify.set({ on: true })
    const src = await listen()
    src.emit('incident.dispatched', { id: 'i1', assignee: 'someone-else' })
    src.emit('incident.dispatched', { id: 'i1', assignee: 'tia' })
    src.emit('incident.changed', { id: 'i1', action: 'created' })
    src.emit('switch.status', { id: 's1', name: 'sw-d-01', status: 'online' })
    src.emit('switch.status', { id: 's1', name: 'sw-d-01', status: 'offline' })
    await waitFor(() => expect(shown).toHaveLength(3))
    expect(shown.map((n) => n.tag).sort()).toEqual(['incident-i1', 'job-i1', 'switch-s1'])
    expect(shown.find((n) => n.tag === 'incident-i1')?.body).toBe('Seat D-6: No link')
  })

  it('shows a service going down and skips what is muted', async () => {
    await crewNotify.set({ on: true })
    const src = await listen([{ switch_id: 's2' }, { switch_id: 'health:dns' }])
    src.emit('health.changed', { changes: [
      { id: 'game3', name: 'Game server 3', status: 'down', previous: 'up', summary: 'Not answering' },
      { id: 'dns', name: 'DNS players', status: 'down', previous: 'up', summary: 'Timeout' },
      { id: 'dhcp', name: 'DHCP players', status: 'up', previous: 'down', summary: '' },
    ] })
    src.emit('switch.status', { id: 's2', name: 'sw-d-02', status: 'offline' })
    src.emit('switch.status', { id: 's1', name: 'sw-d-01', status: 'offline' })
    await waitFor(() => expect(shown).toHaveLength(2))
    await new Promise((r) => setTimeout(r, 20))
    expect(shown.map((n) => [n.title, n.body, n.tag]).sort()).toEqual([
      ['Service down', 'Game server 3: Not answering', 'health-game3'],
      ['Switch down', 'sw-d-01 went offline.', 'switch-s1'],
    ])
  })

  it('leaves out a kind that is switched off', async () => {
    await crewNotify.set({ on: true, kinds: { services: false } })
    const src = await listen()
    src.emit('health.changed', { changes: [{ id: 'game3', name: 'Game server 3', status: 'down', previous: 'up', summary: '' }] })
    src.emit('switch.status', { id: 's1', name: 'sw-d-01', status: 'offline' })
    await waitFor(() => expect(shown.map((n) => n.tag)).toEqual(['switch-s1']))
  })

  it('holds back everything but my jobs during quiet hours, past midnight too', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 10, 14, 23, 30))
    await crewNotify.set({ on: true, quiet: true, quietFrom: '22:00', quietTo: '07:00' })
    const src = await listen()
    expect(crewNotify.quietNow()).toBe(true)
    src.emit('switch.status', { id: 's1', name: 'sw-d-01', status: 'offline' })
    src.emit('incident.changed', { id: 'i1', action: 'created' })
    src.emit('incident.dispatched', { id: 'i1', assignee: 'tia' })
    await waitFor(() => expect(shown.map((n) => n.tag)).toEqual(['job-i1']))

    await crewNotify.set({ urgentInQuiet: false })
    src.emit('incident.dispatched', { id: 'i2', assignee: 'tia' })
    vi.setSystemTime(new Date(2026, 10, 15, 7, 0))
    expect(crewNotify.quietNow()).toBe(false)
    src.emit('switch.status', { id: 's2', name: 'sw-d-02', status: 'offline' })
    await waitFor(() => expect(shown.map((n) => n.tag)).toEqual(['job-i1', 'switch-s2']))
  })

  it('notifies when a watched seat goes down or comes back, and only that seat', async () => {
    await crewNotify.set({ on: true })
    setWatchedSeats(['D-6'])
    const src = await listen()
    src.emit('seats.changed', { seats: [['D-6', 0], ['D-7', 0]] })
    src.emit('seats.changed', { seats: [['D-6', 1]] })
    await waitFor(() => expect(shown).toHaveLength(2))
    expect(shown.map((n) => [n.tag, n.body])).toEqual([['seat-D-6', 'Seat D-6 went offline.'], ['seat-D-6', 'Seat D-6 is online again.']])
  })
})

describe('old settings', () => {
  it('moves what notify.js saved to the shared shape', () => {
    localStorage.setItem('floorbit-notify', JSON.stringify({ on: true, switches: false, quiet: true, quietFrom: '23:00', quietTo: '06:00', jobsInQuiet: false, watch: ['D-6'] }))
    migrate()
    expect(crewNotify.prefs()).toEqual({ on: true, kinds: { switches: false }, quiet: true, quietFrom: '23:00', quietTo: '06:00', urgentInQuiet: false })
    expect(watchedSeats()).toEqual(['D-6'])
  })
})

describe('NotifySettings', () => {
  it('switches notifications on and offers Floorbit\'s kinds', async () => {
    renderWithApp(<NotifySettings opened onClose={() => {}} />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Notify me on this device' }))
    await waitFor(() => expect(crewNotify.prefs().on).toBe(true))
    const box = await screen.findByRole('checkbox', { name: 'A switch going down' })
    expect(box).not.toBeDisabled()
    fireEvent.click(box)
    await waitFor(() => expect(crewNotify.prefs().kinds.switches).toBe(false))
    expect(screen.getByRole('checkbox', { name: /A job sent to me/ })).toBeChecked()
  })
})
