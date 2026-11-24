import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import type { Raw } from './clipboard'
import { PresetsDialog, SavePresetDialog } from './Presets'

afterEach(() => vi.unstubAllGlobals())

const items: Raw[] = [
  { kind: 'mark', body: { kind: 'zone', x: 10, y: 10, w: 20, h: 15, label: 'Admin' } },
  { kind: 'block', body: { name: 'A', x: 15, y: 15, rows: [{ id: '1', seats: 4 }] } },
]
const preset = { id: 'p1', name: 'Admin zone', saved: '2026-11-24T07:00:00+0100', counts: { mark: 1, block: 1 }, items }

describe('plan presets', () => {
  it('keeps the selection under a name', async () => {
    const api = fakeFetch({ 'POST /api/plan-presets': preset })
    vi.stubGlobal('fetch', api.fn)
    const onClose = vi.fn()
    renderWithApp(<SavePresetDialog items={items} onClose={onClose} />)
    expect(await screen.findByText(/these 2 items together/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Name/), { target: { value: ' Admin zone ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save preset' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(api.calls.find((c) => c.method === 'POST')!.body).toEqual({ name: 'Admin zone', items })
  })

  it('lists presets with what they hold, places one and deletes one', async () => {
    const api = fakeFetch({ 'GET /api/plan-presets': { presets: [preset] }, 'DELETE /api/plan-presets/p1': { success: true } })
    vi.stubGlobal('fetch', api.fn)
    const onPlace = vi.fn()
    renderWithApp(<PresetsDialog opened onClose={() => {}} onPlace={onPlace} />)
    expect(await screen.findByText('1 seat block')).toBeInTheDocument()
    expect(screen.getByText('1 mark')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Place “Admin zone”' }))
    expect(onPlace).toHaveBeenCalledWith(preset)
    fireEvent.click(screen.getByRole('button', { name: 'Delete “Admin zone”' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'DELETE')).toBe(true))
  })
})
