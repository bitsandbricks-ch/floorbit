import { act, fireEvent, screen } from '@testing-library/react'
import i18n from 'i18next'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PlanDrawing } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import PublicFind from './PublicFind'

afterEach(() => { vi.unstubAllGlobals(); void i18n.changeLanguage('en'); window.history.replaceState(null, '', '/') })

const drawing: PlanDrawing = {
  box: '0 0 400 200', cell: 32, shapes: [{ cx: 200, cy: 100, rotation: 0, w: 64, h: 32, name: 'D',
    cells: [{ seat: 'D-1', x: -32, y: 0, hit: false, on: null }, { seat: 'D-2', x: 0, y: 0, hit: true, on: null }] }],
}
const found = { nicks: false, found: { seat: 'D-2', block: 'D', row: 1, rows: 1, col: 2, hall: '' }, drawing }

describe('PublicFind', () => {
  it('finds a seat and rings it on the plan', async () => {
    const fake = fakeFetch({ 'GET /api/seat-finder': { nicks: false }, 'GET /api/seat-finder?q=d2': found })
    vi.stubGlobal('fetch', fake.fn)
    const { container } = renderWithApp(<PublicFind />, '/find')
    fireEvent.change(await screen.findByLabelText(/Seat/), { target: { value: ' d2 ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Find' }))
    expect(await screen.findByRole('heading', { name: 'Seat D-2' })).toBeInTheDocument()
    expect(screen.getByText('Block D, row 1 of 1, seat 2 from the left as seen on the plan.')).toBeInTheDocument()
    expect([...container.querySelectorAll('.cell.hit')].map((c) => c.getAttribute('data-seat'))).toEqual(['D-2'])
    expect(container.querySelector('.ring')).not.toBeNull()
  })

  it('says when there is no such seat, and when it is busy', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/seat-finder': { nicks: true },
      'GET /api/seat-finder?q=Z-99': () => ({ status: 404, body: { code: 'none' } }) }).fn)
    renderWithApp(<PublicFind />, '/find?q=Z-99')
    expect(await screen.findByRole('alert')).toHaveTextContent('No seat "Z-99" on the floor plan.')
    expect(screen.getByLabelText(/Seat or nick/)).toBeInTheDocument()
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/seat-finder': { nicks: false },
      'GET /api/seat-finder?q=D-1': () => ({ status: 429, body: { code: 'busy' } }) }).fn)
    renderWithApp(<PublicFind />, '/find?q=D-1')
    expect(await screen.findByText(/Too many searches/)).toBeInTheDocument()
  })

  it('speaks German, and says when it is off', async () => {
    await act(() => i18n.changeLanguage('de-CH'))
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/seat-finder': { nicks: false }, 'GET /api/seat-finder?q=D-2': found }).fn)
    renderWithApp(<PublicFind />, '/find?q=D-2')
    expect(await screen.findByRole('heading', { name: 'Platz D-2' })).toBeInTheDocument()
    await act(() => i18n.changeLanguage('en'))
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/seat-finder': () => ({ status: 404, body: { code: 'off' } }) }).fn)
    renderWithApp(<PublicFind />, '/find')
    expect(await screen.findByRole('alert')).toHaveTextContent('The seat finder is switched off.')
  })
})
