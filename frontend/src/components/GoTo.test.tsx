import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { Route, Routes, useLocation } from 'react-router-dom'
import { AppShell, Layout } from './Layout'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

const tech = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: ['floorplan.view', 'incidents.work'] } }

// What GET /api/pages answers a tech with the power feature off (the server filters, see tests/test_page_index.py).
const pages = { pages: [
  { href: '/', id: 'floorPlan', label: 'Floor plan' },
  { href: '/problems', id: 'problems', label: 'Problems' },
  { href: '/handover', id: 'handover', label: 'Shift handover' },
  { href: '/health', id: 'health', label: 'Service health' },
  { href: '/stats', id: 'stats', label: 'Stats' },
  { href: '/settings/status', id: 'newPage', label: 'Status settings' },
] }

// Shows where the router went: React pages are routes now, so the sidebar stays (no page load).
function Where() {
  const at = useLocation()
  return <output data-testid="where">{at.pathname + at.search}</output>
}

function page(route = '/problems') {
  return renderWithApp(
    <Routes><Route path="*" element={<AppShell><Layout title="Problems" back={{ href: '/', label: 'Floor plan' }}><Where /></Layout></AppShell>} /></Routes>,
    route,
  )
}

// The palette's rows: each group's actions, "label" + "path" as the row shows them.
const rows = (group: string) => within(screen.getByRole('group', { name: group })).getAllByRole('button')
const box = () => screen.findByRole('textbox', { name: 'Jump to' })
const type = async (text: string) => fireEvent.change(await box(), { target: { value: text } })
const key = async (code: string) => fireEvent.keyDown(await box(), { key: code, code })

async function opened(route?: string) {
  const app = page(route)
  await screen.findByRole('button', { name: /Signed in as kim/ })
  fireEvent.click(screen.getByRole('button', { name: /Search pages/ }))
  await box()
  return app
}

describe('Go to', () => {
  it('lists the pages the server offers this account, in this language', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/pages': pages }).fn)
    await opened()
    await waitFor(() => expect(rows('Pages').map((o) => o.textContent)).toContain('Problems/problems'))
    const names = rows('Pages').map((o) => o.textContent)
    expect(names).toContain('Shift handover/handover')
    // A page this version has no text for yet keeps the server's English name.
    expect(names).toContain('Status settings/settings/status')
    expect(names).toHaveLength(pages.pages.length)
  })

  it('opens with Ctrl+K, filters as you type and opens the first match on Enter', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/pages': pages }).fn)
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    page()
    await screen.findByRole('button', { name: /Signed in as kim/ })
    fireEvent.keyDown(document.documentElement, { key: 'k', code: 'KeyK', ctrlKey: true })
    await type('stats')
    await waitFor(() => expect(rows('Pages')[0]).toHaveAttribute('data-selected', 'true'))
    expect(rows('Pages')[0]).toHaveTextContent('Stats')
    await key('Enter')
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/stats'))
    expect(assign).not.toHaveBeenCalled()
  })

  it('finds a page by other words for it too', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/pages': pages }).fn)
    await opened()
    await type('uptime')
    await waitFor(() => expect(rows('Pages').map((o) => o.textContent)).toEqual(['Service health/health']))
  })

  it('loads the floor plan, a page the server draws, in full', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/pages': pages }).fn)
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    await opened()
    await type('floor plan')
    await waitFor(() => expect(rows('Pages')[0]).toHaveAttribute('data-selected', 'true'))
    await key('Enter')
    expect(assign).toHaveBeenCalledWith('/')
  })

  it('says so when nothing matches', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/pages': pages }).fn)
    await opened()
    await type('zzz')
    expect(await screen.findByText('Nothing matches')).toBeInTheDocument()
  })

  it('puts the pages opened last first while nothing is typed', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/pages': pages }).fn)
    localStorage.setItem('floorbit-recent-pages', JSON.stringify(['/health', '/nope']))
    // Opening this page remembers it, but the list leaves out the page you are on.
    await opened('/stats')
    expect(JSON.parse(localStorage.getItem('floorbit-recent-pages')!)).toEqual(['/stats', '/health', '/nope'])
    await waitFor(() => expect(rows('Recent').map((o) => o.textContent)).toEqual(['Service health/health']))
    await type('health')
    await waitFor(() => expect(screen.queryByRole('group', { name: 'Recent' })).toBeNull())
  })

  it('finds seats, switches and players once you type two characters', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': tech, 'GET /api/pages': pages,
      'GET /api/pages/find?q=b8': { places: [
        { kind: 'seat', name: 'B-8', href: '/plan?seat=B-8' },
        { kind: 'switch', name: 'sw-b8', href: '/plan?switch=sw-b8' },
        { kind: 'player', name: 'b8ster · C-3', href: '/plan?seat=C-3' },
      ] },
    })
    vi.stubGlobal('fetch', fake.fn)
    await opened()
    await type('b')
    await type('b8')
    await waitFor(() => expect(rows('Seats, switches and players').map((o) => o.textContent))
      .toEqual(['Seat B-8', 'Switch sw-b8', 'Player b8ster · C-3']))
    // One character never asks the server.
    expect(fake.calls.some((c) => c.path === '/api/pages/find?q=b')).toBe(false)
    fireEvent.click(rows('Seats, switches and players')[0])
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/plan?seat=B-8'))
  })

  it('does what the user menu does', async () => {
    const lead = { enabled: true, user: { ...tech.user, role: 'lead', permissions: [...tech.user.permissions, 'incidents.assign'] } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/pages': pages, 'GET /api/notice': { notice: null } }).fn)
    await opened()
    await waitFor(() => expect(rows('Actions').map((o) => o.textContent)).toContain('Sign out'))
    // ">" leaves only the commands.
    await type('>notice')
    await waitFor(() => expect(screen.queryByRole('group', { name: 'Pages' })).toBeNull())
    expect(rows('Actions')[0]).toHaveTextContent('Put up a crew notice')
    await waitFor(() => expect(rows('Actions')[0]).toHaveAttribute('data-selected', 'true'))
    await key('Enter')
    // The palette closes and the crew notice editor opens.
    expect(await screen.findByRole('dialog', { name: 'Crew notice' })).toBeInTheDocument()
  })
})
