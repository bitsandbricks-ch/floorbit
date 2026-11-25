import { act, fireEvent, renderHook, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '@/i18n'
import { fakeFetch, renderWithApp } from '@/test/render'
import { MergeBlocks, SplitBlock } from './BlockJoin'
import type { Step } from './history'
import { useBlockJoin } from './useBlockJoin'

afterEach(() => vi.unstubAllGlobals())

const A = { id: 'a', name: 'A', x: 40, y: 40, rows: [{ id: '1', seats: 8 }], naming: 'block', hall_id: 'main' }
const B = { id: 'b', name: 'B', x: 56, y: 40, rows: [{ id: '1', seats: 8 }], naming: 'block', hall_id: 'main' }

function setup(routes: Record<string, unknown>) {
  const api = fakeFetch({ 'GET /api/seat-blocks?hall=main': [A, B], ...routes })
  vi.stubGlobal('fetch', api.fn)
  const steps: Step[] = []
  const select = vi.fn()
  const alias = { current: new Map<string, string>() }
  const { result } = renderHook(() => useBlockJoin({
    hall: 'main', push: (s) => steps.push(s), refresh: () => Promise.resolve(), fail: (e) => { throw e }, select,
    idOf: (r) => alias.current.get(`block:${r.id}`) ?? r.id, alias,
  }))
  return { api, steps, select, alias, join: result }
}

describe('merging and splitting seat blocks (#1208)', () => {
  it('merges the picked blocks, and undo puts both back as they were', async () => {
    const { api, steps, select, alias, join } = setup({
      'POST /api/seat-blocks/merge': { block: { ...A, rows: [{ id: '1', seats: 16 }] }, removed: ['b'] },
      'PUT /api/seat-blocks/a': A, 'POST /api/seat-blocks': { id: 'b2' },
    })
    await act(() => join.current.merge(['b', 'a']))
    expect(api.calls.find((c) => c.path === '/api/seat-blocks/merge')?.body).toEqual({ ids: ['b', 'a'] })
    expect(select).toHaveBeenCalledWith([{ kind: 'block', id: 'a' }])
    expect(steps.map((s) => s.label)).toEqual(['merge 2 blocks'])
    await act(() => steps[0].undo())
    const put = api.calls.find((c) => c.method === 'PUT')!
    expect(put.path).toBe('/api/seat-blocks/a')
    expect(put.body).toMatchObject({ name: 'A', x: 40, rows: A.rows })
    expect(api.calls.find((c) => c.method === 'POST' && c.path === '/api/seat-blocks')?.body).toMatchObject({ name: 'B', x: 56, hall_id: 'main' })
    // Redo merges the block that came back under its new id.
    expect(alias.current.get('block:b')).toBe('b2')
  })

  it('splits a block above a row, and undo joins it again', async () => {
    const { api, steps, select, join } = setup({
      'POST /api/seat-blocks/a/split': { block: { id: 'a' }, new: { id: 'c' } },
      'DELETE /api/seat-blocks/c': { success: true }, 'PUT /api/seat-blocks/a': A,
    })
    await act(() => join.current.split('a', 1))
    expect(api.calls.find((c) => c.path === '/api/seat-blocks/a/split')?.body).toEqual({ at: 1 })
    expect(select).toHaveBeenCalledWith([{ kind: 'block', id: 'a' }, { kind: 'block', id: 'c' }])
    await act(() => steps[0].undo())
    expect(api.calls.slice(-2).map((c) => `${c.method} ${c.path}`)).toEqual(['DELETE /api/seat-blocks/c', 'PUT /api/seat-blocks/a'])
  })

  it('offers the split above any row but the first', () => {
    const onSplit = vi.fn()
    const first = renderWithApp(<SplitBlock index={0} name="C" freely={false} onSplit={onSplit} />)
    expect(screen.queryByRole('button')).toBeNull()
    first.unmount()
    renderWithApp(<SplitBlock index={1} name="D" freely={false} onSplit={onSplit} />)
    fireEvent.click(screen.getByRole('button', { name: 'Split block above row D' }))
    expect(onSplit).toHaveBeenCalled()
  })

  it('names how many blocks merge', () => {
    renderWithApp(<MergeBlocks count={3} onMerge={() => {}} />)
    expect(screen.getByRole('button', { name: 'Merge 3 blocks' })).toBeTruthy()
  })
})
