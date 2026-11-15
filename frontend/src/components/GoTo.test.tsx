import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { Layout } from './Layout'

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

function page(route = '/problems') {
  return renderWithApp(<Layout title="Problems" back={{ href: '/', label: 'Floor plan' }}>body</Layout>, route)
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
    expect(assign).toHaveBeenCalledWith(options[1].querySelector('.fb-goto-path')!.textContent)
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
      ] },
    })
    vi.stubGlobal('fetch', fake.fn)
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    page()
    fireEvent.click(await screen.findByRole('button', { name: /Go to/ }))
    const box = await screen.findByRole('combobox')
    fireEvent.change(box, { target: { value: 'b' } })
    fireEvent.change(box, { target: { value: 'b8' } })
    const seat = await screen.findByRole('option', { name: /Seat B-8/ })
    expect(screen.getByRole('option', { name: /Switch sw-b8/ })).toBeInTheDocument()
    // One character never asks the server.
    expect(fake.calls.some((c) => c.path === '/api/pages/find?q=b')).toBe(false)
    expect(seat).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(assign).toHaveBeenCalledWith('/plan?seat=B-8')
  })
})
