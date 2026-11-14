import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Hall, LayoutTemplate } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import Templates from './Templates'

afterEach(() => vi.unstubAllGlobals())

const editor = { enabled: true, user: { username: 'kim', display_name: 'Kim', role: 'lead', permissions: ['floorplan.view', 'floorplan.edit'] } }
const viewer = { enabled: true, user: { username: 'vic', display_name: 'Vic', role: 'viewer', permissions: ['floorplan.view'] } }
const halls: Hall[] = [
  { id: 'main', name: 'Main hall', background: null, switches: 3, seat_blocks: 4 },
  { id: 'up', name: 'Upper floor', background: null, switches: 0, seat_blocks: 2 },
]
const tpl: LayoutTemplate = {
  id: 'abcdef123456', name: 'Spring layout', description: 'Four blocks', created: '2026-11-14T08:00:00+0000', updated: '2026-11-14T09:00:00+0000',
  versions: [
    { n: 1, saved: '2026-11-14T08:00:00+0000', halls: 1, switches: 3, seat_blocks: 4 },
    { n: 2, saved: '2026-11-14T09:00:00+0000', halls: 1, switches: 3, seat_blocks: 5 },
  ],
}

describe('Templates', () => {
  it('lists templates with their versions', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': editor, 'GET /api/templates': { templates: [tpl] }, 'GET /api/halls': { halls } }).fn)
    renderWithApp(<Templates />)
    expect(await screen.findByRole('heading', { name: /Spring layout/ })).toBeInTheDocument()
    expect(screen.getByText('5 seat blocks')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /v1, 2026-11-14 08:00/ })).toHaveAttribute('href', '/api/templates/abcdef123456/export?version=1')
    expect(screen.getByRole('button', { name: 'Save floor plan as template' })).toBeInTheDocument()
  })

  it('starts a one-hall template in the chosen hall', async () => {
    const fake = fakeFetch({
      'GET /api/auth/me': editor, 'GET /api/templates': { templates: [tpl] }, 'GET /api/halls': { halls },
      'POST /api/templates/abcdef123456/apply': { halls: 1, seat_blocks: 5, switches_placed: 3, switches_added: 0 },
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<Templates />)
    fireEvent.click(await screen.findByRole('button', { name: 'Start from this' }))
    fireEvent.click(await screen.findByRole('radio', { name: 'Upper floor' }))
    expect(screen.getByText(/replaces what is in Upper floor/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Replace the floor plan' }))
    expect(await screen.findByText(/5 seat block\(s\), 3 switch\(es\) placed/)).toBeInTheDocument()
    await waitFor(() => expect(fake.calls).toContainEqual(expect.objectContaining({
      method: 'POST', path: '/api/templates/abcdef123456/apply', body: { version: 2, hall: 'up' } })))
  })

  it('only shows downloads to viewers', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/auth/me': viewer, 'GET /api/templates': { templates: [tpl] }, 'GET /api/halls': { halls } }).fn)
    renderWithApp(<Templates />)
    expect(await screen.findByRole('link', { name: /Download/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start from this' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save floor plan as template' })).not.toBeInTheDocument()
  })
})
