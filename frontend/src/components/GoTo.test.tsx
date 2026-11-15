import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { Layout } from './Layout'

afterEach(() => vi.unstubAllGlobals())

const tech = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'tech', permissions: ['floorplan.view', 'incidents.work'] } }

function page() {
  return renderWithApp(<Layout title="Problems" back={{ href: '/', label: 'Floor plan' }}>body</Layout>)
}

describe('Go to', () => {
  it('lists the pages this account may open, without the features that are off', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/features': { off: ['power'] } }).fn)
    page()
    await screen.findByRole('button', { name: /Signed in as kim/ })
    fireEvent.click(screen.getByRole('button', { name: /Go to/ }))
    const list = await screen.findByRole('listbox')
    const names = () => within(list).getAllByRole('option').map((o) => o.textContent)
    await waitFor(() => expect(names().some((n) => n?.startsWith('Electrics'))).toBe(false)) // feature off
    expect(names()).toContain('Problems/problems')
    expect(names()).toContain('Shift handover/handover')
    expect(names().some((n) => n?.startsWith('Settings'))).toBe(false) // needs settings.manage
  })

  it('filters as you type, moves with the arrows and opens on Enter', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/features': { off: [] } }).fn)
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    page()
    await screen.findByRole('button', { name: /Signed in as kim/ })
    // Ctrl+K opens it from anywhere on the page.
    fireEvent.keyDown(document.documentElement, { key: 'k', code: 'KeyK', ctrlKey: true })
    const box = await screen.findByRole('combobox')
    fireEvent.change(box, { target: { value: 'st' } })
    const options = within(screen.getByRole('listbox')).getAllByRole('option')
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
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': tech, 'GET /api/features': { off: [] } }).fn)
    page()
    fireEvent.click(await screen.findByRole('button', { name: /Go to/ }))
    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'zzz' } })
    expect(screen.getByText('No page matches.')).toBeInTheDocument()
  })
})
