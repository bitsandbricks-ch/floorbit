import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeFetch, renderWithApp } from '@/test/render'
import { VersionsDialog } from './VersionsDialog'

afterEach(() => vi.unstubAllGlobals())

const v = (id: string, name: string, halls: number) => ({
  id, name, description: '', created: '2026-11-17T10:00:00+0000', updated: `2026-11-17T1${id}:00:00+0000`,
  versions: [{ n: 1, saved: '2026-11-17T10:00:00+0000', halls, switches: 2, seat_blocks: 4 }],
})

describe('plan versions', () => {
  it('lists one-hall versions, keeps the plan as it was and restores into this hall', async () => {
    const api = fakeFetch({
      'GET /api/templates': { templates: [v('1', 'Friday', 1), v('2', 'Whole event', 3)] },
      'POST /api/templates': { id: 'new' },
      'POST /api/templates/1/apply': { halls: 1, seat_blocks: 4, switches_placed: 2, switches_added: 0 },
    })
    vi.stubGlobal('fetch', api.fn)
    const onRestored = vi.fn(() => Promise.resolve())
    renderWithApp(<VersionsDialog opened hall="main" hallName="Hall" onClose={() => {}} onRestored={onRestored} />)
    expect(await screen.findByText('Friday')).toBeInTheDocument()
    expect(screen.queryByText('Whole event')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Restore' }))
    fireEvent.click(screen.getByRole('button', { name: 'Replace this hall\'s plan' }))
    await waitFor(() => expect(onRestored).toHaveBeenCalled())
    const posts = api.calls.filter((c) => c.method === 'POST')
    expect(posts.map((c) => c.path)).toEqual(['/api/templates', '/api/templates/1/apply'])
    expect(posts[0].body).toMatchObject({ hall: 'main', name: expect.stringContaining('Before restoring “Friday”') })
    expect(posts[1].body).toEqual({ hall: 'main' })
  })

  it('saves the hall under the name given', async () => {
    const api = fakeFetch({ 'GET /api/templates': { templates: [] }, 'POST /api/templates': { id: 'new' } })
    vi.stubGlobal('fetch', api.fn)
    renderWithApp(<VersionsDialog opened hall="main" hallName="Hall" onClose={() => {}} onRestored={() => Promise.resolve()} />)
    fireEvent.change(await screen.findByLabelText('Name'), { target: { value: 'Before doors open' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save this version' }))
    await waitFor(() => expect(api.calls.some((c) => c.method === 'POST')).toBe(true))
    expect(api.calls.find((c) => c.method === 'POST')!.body).toEqual({ name: 'Before doors open', hall: 'main' })
  })
})
