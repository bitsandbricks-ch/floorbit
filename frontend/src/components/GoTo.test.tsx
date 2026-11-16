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

describe('Go to', () => {
  it('lists the pages the server offers this account, in this language', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/pages': pages }).fn)
    page()
    await screen.findByRole('button', { name: /Signed in as kim/ })
    fireEvent.click(screen.getByRole('button', { name: /Go to/ }))
    const list = await screen.findByRole('listbox')
    const names = () => within(list).getAllByRole('option').map((o) => o.textContent)
    await waitFor(() => expect(names()).toContain('Problems/problems'))
    expect(names()).toContain('Shift handover/handover')
    // A page this version has no text for yet keeps the server's English name.
    expect(names()).toContain('Status settings/settings/status')
    expect(names()).toHaveLength(pages.pages.length)
  })

  it('filters as you type, moves with the arrows and opens on Enter', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/pages': pages }).fn)
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    page()
    await screen.findByRole('button', { name: /Signed in as kim/ })
    // Ctrl+K opens it from anywhere on the page.
    fireEvent.keyDown(document.documentElement, { key: 'k', code: 'KeyK', ctrlKey: true })
    const box = await screen.findByRole('combobox')
    fireEvent.change(box, { target: { value: 'st' } })
    const options = within(await screen.findByRole('listbox')).getAllByRole('option')
    // Label matches first: Stats before pages that only match by path.
    expect(options[0]).toHaveTextContent('Stats')
    expect(options[0]).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(box, { key: 'ArrowDown' })
    expect(options[1]).toHaveAttribute('aria-selected', 'true')
    expect(box).toHaveAttribute('aria-activedescendant', options[1].id)
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(screen.getByTestId('where')).toHaveTextContent(options[1].querySelector('.fb-goto-path')!.textContent!)
    expect(assign).not.toHaveBeenCalled()
  })

  it('loads the floor plan, a page the server draws, in full', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/pages': pages }).fn)
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    page()
    fireEvent.click(await screen.findByRole('button', { name: /Go to/ }))
    const box = await screen.findByRole('combobox')
    fireEvent.change(box, { target: { value: 'floor' } })
    await screen.findByRole('option', { name: /Floor plan/ })
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(assign).toHaveBeenCalledWith('/')
  })

  it('says so when nothing matches', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/pages': pages }).fn)
    page()
    fireEvent.click(await screen.findByRole('button', { name: /Go to/ }))
    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'zzz' } })
    expect(await screen.findByText('Nothing matches.')).toBeInTheDocument()
  })

  it('puts the pages opened last first while nothing is typed', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/pages': pages }).fn)
    localStorage.setItem('floorbit-recent-pages', JSON.stringify(['/health', '/nope']))
    // Opening this page remembers it, but the list leaves out the page you are on.
    page('/stats')
    expect(JSON.parse(localStorage.getItem('floorbit-recent-pages')!)).toEqual(['/stats', '/health', '/nope'])
    fireEvent.click(await screen.findByRole('button', { name: /Go to/ }))
    const options = within(await screen.findByRole('listbox')).getAllByRole('option')
    expect(options[0]).toHaveTextContent('Service health · recent/health')
    expect(options.some((o) => o.textContent?.startsWith('Stats · recent'))).toBe(false)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'health' } })
    expect(screen.getAllByRole('option')[0]).toHaveTextContent(/^Service health\/health$/)
  })

  it('finds seats and switches once you type two characters', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': tech, 'GET /api/pages': pages,
      'GET /api/pages/find?q=b8': { places: [
        { kind: 'seat', name: 'B-8', href: '/plan?seat=B-8' },
        { kind: 'switch', name: 'sw-b8', href: '/plan?switch=sw-b8' },
        { kind: 'player', name: 'b8ster · C-3', href: '/plan?seat=C-3' },
      ] },
    })
    vi.stubGlobal('fetch', fake.fn)
    page()
    fireEvent.click(await screen.findByRole('button', { name: /Go to/ }))
    const box = await screen.findByRole('combobox')
    fireEvent.change(box, { target: { value: 'b' } })
    fireEvent.change(box, { target: { value: 'b8' } })
    const seat = await screen.findByRole('option', { name: /Seat B-8/ })
    expect(screen.getByRole('option', { name: /Switch sw-b8/ })).toBeInTheDocument()
    // A player by nick, IP or MAC, when the account may see people (issue #292).
    expect(screen.getByRole('option', { name: /Player b8ster · C-3/ })).toBeInTheDocument()
    // One character never asks the server.
    expect(fake.calls.some((c) => c.path === '/api/pages/find?q=b')).toBe(false)
    expect(seat).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(screen.getByTestId('where')).toHaveTextContent('/plan?seat=B-8')
  })

  it('does what the user menu does, once you type it', async () => {
    const lead = { enabled: true, user: { ...tech.user, role: 'lead', permissions: [...tech.user.permissions, 'incidents.assign'] } }
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': lead, 'GET /api/pages': pages, 'GET /api/notice': { notice: null } }).fn)
    page()
    await screen.findByRole('button', { name: /Signed in as kim/ })
    fireEvent.click(screen.getByRole('button', { name: /Go to/ }))
    const box = await screen.findByRole('combobox')
    // Nothing typed: pages only.
    expect(screen.queryByRole('option', { name: /Sign out/ })).toBeNull()
    fireEvent.change(box, { target: { value: 'sign' } })
    expect(await screen.findByRole('option', { name: /Sign outAction/ })).toBeInTheDocument()
    fireEvent.change(box, { target: { value: 'notice' } })
    expect(await screen.findByRole('option', { name: /Put up a crew notice/ })).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(box, { key: 'Enter' })
    // The palette closes and the crew notice editor opens.
    expect(await screen.findByRole('dialog', { name: 'Crew notice' })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('combobox', { name: /Type a page/ })).toBeNull())
  })
})
