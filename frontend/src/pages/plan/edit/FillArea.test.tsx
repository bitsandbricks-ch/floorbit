import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { FillAreaDialog, type FillOptions } from './FillAreaDialog'
import { TOOL_GESTURE, TOOL_KEYS } from './tools'

afterEach(() => vi.unstubAllGlobals())

const box = { x: 10, y: 10, w: 48, h: 25.6 }

function dialog(preview: (body: Record<string, unknown>) => { status?: number; body: unknown }) {
  const fake = fakeFetch({
    // Rows A and B are taken, so the fill starts at C.
    'GET /api/seat-blocks': [{ naming: 'rows', row_start: 'A', rows: 2 }],
    'POST /api/seat-blocks/fill': (init?: RequestInit) => preview(JSON.parse(String(init?.body))),
  })
  vi.stubGlobal('fetch', fake.fn)
  const onFill = vi.fn<(opts: FillOptions) => Promise<boolean>>(() => Promise.resolve(true))
  renderWithApp(<FillAreaDialog box={box} hall="h1" onClose={() => {}} onFill={onFill} />)
  return { onFill, calls: fake.calls }
}

describe('Fill area (#1565)', () => {
  it('is a box tool on A', () => {
    expect(TOOL_GESTURE.fill).toBe('box')
    expect(TOOL_KEYS.fill).toBe('a')
  })

  it('says what the box takes and fills it with runs of two rows from the next free row', async () => {
    const { onFill, calls } = dialog(() => ({ body: { blocks: 4, marks: 2, seats: 80 } }))
    expect(await screen.findByText('4 runs, 80 seats, 2 walkways')).toBeInTheDocument()
    const asked = calls.find((c) => c.method === 'POST')!.body as Record<string, unknown>
    expect(asked).toMatchObject({ ...box, hall_id: 'h1', preview: true, rows: 2, spacer: 1, walkway: 2, row_start: 'C' })
    fireEvent.click(screen.getByRole('button', { name: 'Fill' }))
    await waitFor(() => expect(onFill).toHaveBeenCalledWith({ seats: 10, rows: 2, spacer: 1, walkway: 2, row_start: 'C', labels: true }))
  })

  it('says when the box is too small and does not fill it', async () => {
    dialog(() => ({ status: 400, body: { error: 'The area is too small for one run of seats' } }))
    expect(await screen.findByText('The area is too small for one run of seats')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fill' })).toBeDisabled()
  })
})
