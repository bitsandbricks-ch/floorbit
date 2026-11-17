import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useHistory } from './history'

const steps = (log: string[]) => ['a', 'b', 'c', 'd'].map((label) => ({
  label, undo: async () => { log.push(`-${label}`) }, redo: async () => { log.push(`+${label}`) },
}))

describe('the editor history list', () => {
  it('lists undone steps above done ones, newest first', async () => {
    const { result } = renderHook(() => useHistory())
    act(() => steps([]).forEach((s) => result.current.push(s)))
    await act(() => result.current.jump('undo', 1))
    expect(result.current.future).toEqual(['d'])
    expect(result.current.past).toEqual(['c', 'b', 'a'])
  })
  it('jumps several steps back and forward in order', async () => {
    const log: string[] = []
    const { result } = renderHook(() => useHistory())
    act(() => steps(log).forEach((s) => result.current.push(s)))
    await act(() => result.current.jump('undo', 3))
    expect(log).toEqual(['-d', '-c', '-b'])
    expect(result.current.future).toEqual(['d', 'c', 'b'])
    await act(() => result.current.jump('redo', 2))
    expect(log.slice(3)).toEqual(['+b', '+c'])
    expect(result.current.past).toEqual(['c', 'b', 'a'])
  })
  it('stops at a step that fails, keeping the ones already undone', async () => {
    const log: string[] = []
    const { result } = renderHook(() => useHistory())
    const [a, b, c] = steps(log)
    act(() => { result.current.push(a); result.current.push({ ...b, undo: async () => { throw new Error('offline') } }); result.current.push(c) })
    await act(async () => { await expect(result.current.jump('undo', 3)).rejects.toThrow('offline') })
    expect(log).toEqual(['-c'])
    expect(result.current.past).toEqual(['b', 'a'])
  })
})
