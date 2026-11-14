import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderWithApp } from '@/test/render'
import notifySource from '../../../static/js/notify.js?raw'
import { NotifySettings } from './NotifySettings'

afterEach(() => {
  vi.unstubAllGlobals()
  delete window.floorNotify
  localStorage.clear()
})

class FakeSource {
  static last: FakeSource | null = null
  handlers: Record<string, (e: { data: string }) => void> = {}
  constructor() { FakeSource.last = this }
  addEventListener(type: string, fn: (e: { data: string }) => void) { this.handlers[type] = fn }
  close() {}
  emit(type: string, data: unknown) { this.handlers[type]?.({ data: JSON.stringify({ type, data }) }) }
}

function loadNotify(shown: { title: string; body: string; tag: string }[]) {
  const Note = vi.fn(function (this: object, title: string, opts: { body: string; tag: string }) { shown.push({ title, ...opts }) }) as unknown as typeof Notification
  Object.assign(Note, { permission: 'granted', requestPermission: async () => 'granted' })
  vi.stubGlobal('Notification', Note)
  vi.stubGlobal('EventSource', FakeSource)
  vi.stubGlobal('fetch', vi.fn(async (path: string) => ({
    ok: true,
    json: async () => path === '/api/auth/me'
      ? { user: { username: 'tia' } }
      : { incidents: [{ id: 'i1', seat: 'D-6', title: 'No link' }] },
  })))
  // static/js/notify.js is a classic script for the editor and the React pages alike.
  new Function(notifySource)()
}

describe('notify.js', () => {
  it('shows a job for me, a new incident and a switch going down once switched on', async () => {
    const shown: { title: string; body: string; tag: string }[] = []
    loadNotify(shown)
    expect(window.floorNotify!.settings().on).toBe(false)
    await window.floorNotify!.set({ on: true })
    await waitFor(() => expect(FakeSource.last?.handlers['switch.status']).toBeTruthy())
    const src = FakeSource.last!
    src.emit('incident.dispatched', { id: 'i1', assignee: 'someone-else' })
    src.emit('incident.dispatched', { id: 'i1', assignee: 'tia' })
    src.emit('incident.changed', { id: 'i1', action: 'created' })
    src.emit('switch.status', { id: 's1', name: 'sw-d-01', status: 'online' })
    src.emit('switch.status', { id: 's1', name: 'sw-d-01', status: 'offline' })
    await waitFor(() => expect(shown).toHaveLength(3))
    expect(shown.map((n) => n.tag).sort()).toEqual(['incident-i1', 'job-i1', 'switch-s1'])
    expect(shown.find((n) => n.tag === 'incident-i1')?.body).toBe('Seat D-6: No link')
    expect(JSON.parse(localStorage.getItem('floorbit-notify')!).on).toBe(true)
  })
})

describe('NotifySettings', () => {
  it('switches notifications on through notify.js', async () => {
    const set = vi.fn(async (c: object) => ({ on: true, incidents: true, jobs: true, switches: true, ...c }))
    window.floorNotify = {
      supported: () => true, permission: () => 'granted', set,
      settings: () => ({ on: false, incidents: true, jobs: true, switches: true }),
    }
    renderWithApp(<NotifySettings opened onClose={() => {}} />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Notifications on this device' }))
    await waitFor(() => expect(set).toHaveBeenCalledWith({ on: true }))
    expect(await screen.findByRole('checkbox', { name: 'A switch going down' })).not.toBeDisabled()
  })
})
