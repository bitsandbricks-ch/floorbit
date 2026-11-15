import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { Layout } from './Layout'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

const now = Date.now() / 1000
const notice = { text: 'Hall B: power work at 14:00, leave row C alone', level: 'warn', until: now + 3600, by: 'Lea', at: now }
const tech = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: ['incidents.work'] } }
const lead = { enabled: true, user: { username: 'lea', display_name: 'Lea', role: 'lead', permissions: ['incidents.work', 'incidents.assign'] } }

function page() {
  return renderWithApp(<Layout title="Problems" back={{ href: '/', label: 'Floor plan' }}>body</Layout>, '/problems')
}

describe('Crew notice', () => {
  it('shows the notice under the header, and each person can hide it', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/notice': { notice } }).fn)
    page()
    const banner = await screen.findByRole('status')
    expect(banner).toHaveTextContent('Hall B: power work at 14:00, leave row C alone')
    expect(banner).toHaveTextContent(/Lea, .* · until /)
    fireEvent.click(screen.getByRole('button', { name: 'Hide this notice' }))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(localStorage.getItem('floorbit-notice-hidden')).toBe(String(now))
  })

  it('shows nothing when there is no notice, and techs have no menu entry', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/notice': { notice: null } }).fn)
    page()
    fireEvent.click(await screen.findByRole('button', { name: /Signed in as kim/ }))
    expect(await screen.findByRole('menuitem', { name: 'Notifications' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Crew notice' })).not.toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('lets a lead put one up', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': lead,
      'GET /api/notice': { notice: null },
      'PUT /api/notice': (init: RequestInit | undefined) => ({ body: { notice: { ...JSON.parse(String(init?.body)), until: null, by: 'Lea', at: now } } }),
    })
    vi.stubGlobal('fetch', fake.fn)
    page()
    fireEvent.click(await screen.findByRole('button', { name: /Signed in as lea/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Crew notice' }))
    fireEvent.change(await screen.findByLabelText(/Message/), { target: { value: 'Doors open at 18:00' } })
    fireEvent.click(screen.getByRole('radio', { name: 'Warning' }))
    fireEvent.click(screen.getByRole('button', { name: 'Put up' }))
    await waitFor(() => expect(fake.calls.find((c) => c.method === 'PUT')?.body).toEqual({ text: 'Doors open at 18:00', level: 'warn', hours: 0 }))
    expect(await screen.findByRole('status')).toHaveTextContent('Doors open at 18:00')
  })
})
