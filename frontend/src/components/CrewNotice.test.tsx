import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { AppShell, Layout } from './Layout'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

const now = Date.now() / 1000
const notice = { text: 'Hall B: power work at 14:00, leave row C alone', level: 'warn', until: now + 3600, by: 'Lea', at: now }
const tech = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: ['incidents.work'] } }
const lead = { enabled: true, user: { username: 'lea', display_name: 'Lea', role: 'lead', permissions: ['incidents.work', 'incidents.assign'] } }

function page() {
  return renderWithApp(<AppShell><Layout title="Problems" back={{ href: '/', label: 'Floor plan' }}>body</Layout></AppShell>, '/problems')
}

describe('Crew notice', () => {
  // The top bar's badge is the last one; the phone header has a compact one too.
  const badge = async (text = notice.text) => {
    await screen.findByRole('button', { name: /Signed in as/ })   // the shell has settled
    return (await screen.findAllByRole('button', { name: `Crew notice: ${text}` })).at(-1)!
  }

  it('shows the notice as a badge in the top bar, and each person can mark it read', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/notice': { notice } }).fn)
    page()
    const b = await badge()
    expect(b).toHaveClass('is-warn')
    fireEvent.click(b)
    const read = await screen.findByRole('button', { name: 'Mark as read' })
    const pop = read.closest('[role="dialog"]')!
    expect(pop).toHaveTextContent('Hall B: power work at 14:00, leave row C alone')
    expect(pop).toHaveTextContent(/Lea, .* · until /)
    expect(screen.queryByRole('button', { name: 'Take down' })).not.toBeInTheDocument()
    fireEvent.click(read)
    expect(localStorage.getItem('floorbit-notice-hidden')).toBe(String(now))
    expect(await badge()).toHaveClass('is-quiet')
  })

  it('lets a lead take it down from the badge', async () => {
    const fake = fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/notice': { notice }, 'DELETE /api/notice': { notice: null } })
    vi.stubGlobal('fetch', fake.fn)
    page()
    fireEvent.click(await badge())
    fireEvent.click(await screen.findByRole('button', { name: 'Take down' }))
    await waitFor(() => expect(fake.calls.some((c) => c.method === 'DELETE')).toBe(true))
    await waitFor(() => expect(screen.queryByRole('button', { name: /^Crew notice:/ })).not.toBeInTheDocument())
  })

  it('shows nothing when there is no notice, and techs have no menu entry', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/notice': { notice: null } }).fn)
    page()
    fireEvent.click(await screen.findByRole('button', { name: /Signed in as kim/ }))
    expect(await screen.findByRole('menuitem', { name: 'Notifications' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Crew notice' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Crew notice:/ })).not.toBeInTheDocument()
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
    expect(await badge('Doors open at 18:00')).toHaveClass('is-warn')
  })
})
