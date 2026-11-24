import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SeatViewData } from '@/api/types'
import { fakeFetch, renderWithApp } from '@/test/render'
import { hallIsEmpty } from './emptyHall'
import { EmptyHall, PlanDialogs, PlanMenu } from './PlanMenu'

afterEach(() => vi.unstubAllGlobals())

const plan = {
  hall: 'side', halls: [{ id: 'main', name: 'Main hall' }, { id: 'side', name: 'Side hall' }],
  blocks: [], switches: [], panels: [], boards: [], background: null, drawing: { shapes: [], marks: [] },
} as unknown as SeatViewData

const tpl = {
  id: 't1', name: 'Club LAN', description: 'Two halls, 120 seats', created: '2026-11-20T10:00:00+0000', updated: '2026-11-20T10:00:00+0000',
  versions: [{ n: 1, saved: '2026-11-20T10:00:00+0000', halls: 1, switches: 3, seat_blocks: 4 }],
}

describe('the editor Plan menu', () => {
  it('opens each dialog', async () => {
    for (const [item, dialog] of [['Save as template…', 'save'], ['Start from a template…', 'start'], ['Place a preset…', 'presets'], ['Versions of this hall…', 'versions'], ['Halls…', 'halls']]) {
      const onOpen = vi.fn()
      const { unmount } = renderWithApp(<PlanMenu onOpen={onOpen} />)
      fireEvent.click(screen.getByRole('button', { name: 'Plan' }))
      fireEvent.click(await screen.findByRole('menuitem', { name: item }))
      expect(onOpen).toHaveBeenCalledWith(dialog)
      unmount()
    }
  })

  it('saves this hall as a template by default', async () => {
    const api = fakeFetch({ 'POST /api/templates': { ...tpl, id: 'new' } })
    vi.stubGlobal('fetch', api.fn)
    const onClose = vi.fn()
    renderWithApp(<PlanDialogs open="save" data={plan} onClose={onClose} onHall={() => {}} onChanged={() => Promise.resolve()} onReplaced={() => Promise.resolve()} onPlace={() => {}} />)
    fireEvent.change(await screen.findByLabelText(/Name/), { target: { value: 'Club LAN' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(api.calls.find((c) => c.method === 'POST')!.body).toEqual({ name: 'Club LAN', description: '', hall: 'side' })
  })

  it('starts this hall from a template and clears what could be undone', async () => {
    const api = fakeFetch({
      'GET /api/templates': { templates: [tpl] },
      'POST /api/templates/t1/apply': { halls: 1, seat_blocks: 4, switches_placed: 3, switches_added: 0 },
    })
    vi.stubGlobal('fetch', api.fn)
    const onReplaced = vi.fn(() => Promise.resolve())
    renderWithApp(<PlanDialogs open="start" data={plan} onClose={() => {}} onHall={() => {}} onChanged={() => Promise.resolve()} onReplaced={onReplaced} onPlace={() => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Start from “Club LAN”' }))
    expect(await screen.findByRole('radio', { name: 'Side hall' })).toBeChecked()
    fireEvent.click(screen.getByRole('button', { name: 'Replace the floor plan' }))
    await waitFor(() => expect(onReplaced).toHaveBeenCalled())
    expect(api.calls.find((c) => c.method === 'POST')!.body).toEqual({ version: 1, hall: 'side' })
  })

  it('offers a template in an empty hall', () => {
    expect(hallIsEmpty(plan)).toBe(true)
    expect(hallIsEmpty({ ...plan, blocks: [{}] } as unknown as SeatViewData)).toBe(false)
    const onStart = vi.fn()
    renderWithApp(<EmptyHall onStart={onStart} />)
    fireEvent.click(screen.getByRole('button', { name: 'Start from a template…' }))
    expect(onStart).toHaveBeenCalled()
  })
})
