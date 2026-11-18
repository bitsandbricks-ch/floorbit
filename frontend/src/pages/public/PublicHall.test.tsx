import { act, fireEvent, screen } from '@testing-library/react'
import i18n from 'i18next'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PlanDrawing } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import PublicHall, { type PublicHallData } from './PublicHall'

afterEach(() => { vi.unstubAllGlobals(); void i18n.changeLanguage('en'); window.history.replaceState(null, '', '/') })

const cell = (seat: string, x: number, on: boolean | null) => ({ seat, x, y: 0, hit: false, on })
const drawing: PlanDrawing = {
  box: '0 0 400 200', cell: 32, shapes: [{ id: 'd', cx: 200, cy: 100, rotation: 0, w: 64, h: 32, name: 'D',
    cells: [cell('D-1', -32, true), cell('D-2', 0, false)], rows: [{ text: 'A', x: -48, y: 16 }] }],
  marks: [{ kind: 'text', x: 100, y: 20, text: 'Stage', size: 'm' }],
}
const hall = (over: Partial<PublicHallData> = {}): PublicHallData => ({
  hall: 'main', halls: [], drawing, online: 1, total: 2, updated: Date.now() / 1000, finder: true, agenda: true, ...over,
})

describe('PublicHall', () => {
  it('marks the online seats and counts them', async () => {
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/public/hall': hall() }).fn)
    const { container } = renderWithApp(<PublicHall />, '/hall')
    expect(await screen.findByText('1 of 2 seats online')).toBeInTheDocument()
    expect([...container.querySelectorAll('.cell.on')].map((c) => c.getAttribute('data-seat'))).toEqual(['D-1'])
    expect(screen.getByText('Stage')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Find your seat' })).toHaveAttribute('href', '/find')
    expect(screen.getByRole('link', { name: 'Schedule' })).toHaveAttribute('href', '/agenda')
  })

  it('says when the status is not known, and switches halls', async () => {
    const fake = fakeFetch({
      'GET /api/public/hall': hall({ online: null, halls: [{ id: 'main', name: 'Main' }, { id: 'side', name: 'Side hall' }] }),
      'GET /api/public/hall?hall=side': hall({ hall: 'side', drawing: null, halls: [{ id: 'main', name: 'Main' }, { id: 'side', name: 'Side hall' }] }),
    })
    vi.stubGlobal('fetch', fake.fn)
    renderWithApp(<PublicHall />, '/hall')
    expect(await screen.findByText(/not available right now/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: 'Side hall' }))
    expect(await screen.findByText('There is no hall plan yet.')).toBeInTheDocument()
  })

  it('speaks German, and says when it is off', async () => {
    await act(() => i18n.changeLanguage('de-CH'))
    vi.stubGlobal('fetch', fakeFetch({ 'GET /api/public/hall': hall() }).fn)
    renderWithApp(<PublicHall />, '/hall')
    expect(await screen.findByText('1 von 2 Plätzen online')).toBeInTheDocument()
    await act(() => i18n.changeLanguage('en'))
    vi.stubGlobal('fetch', fakeFetch({}).fn)
    renderWithApp(<PublicHall />, '/hall')
    expect(await screen.findByRole('alert')).toHaveTextContent('This page is switched off.')
  })
})
