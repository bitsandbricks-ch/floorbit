import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { freshIds, useProblemSound } from './sound'

/** Just enough of an AudioContext to count the tones and say whether the browser lets it play. */
function fakeAudio(startState: 'running' | 'suspended') {
  const tones = { count: 0 }
  class FakeContext extends EventTarget {
    state: string = startState
    currentTime = 0
    destination = {}
    resume = vi.fn(async () => { if (startState === 'running') this.state = 'running'; this.dispatchEvent(new Event('statechange')) })
    close = vi.fn(async () => {})
    createOscillator() {
      tones.count += 1
      return { type: '', frequency: { value: 0 }, connect: (n: unknown) => n, start() {}, stop() {} }
    }
    createGain() {
      return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect: (n: unknown) => n }
    }
  }
  vi.stubGlobal('AudioContext', FakeContext)
  return tones
}

afterEach(() => vi.unstubAllGlobals())

describe('freshIds', () => {
  it('lists what was not there before', () => {
    expect(freshIds(new Set(['a']), ['a', 'b'])).toEqual(['b'])
    expect(freshIds(new Set(['a', 'b']), ['a'])).toEqual([])
  })
})

describe('useProblemSound', () => {
  it('rings once for each new problem, not for what was down when the screen opened', async () => {
    const tones = fakeAudio('running')
    const { rerender } = renderHook(({ ids }) => useProblemSound(true, ids), { initialProps: { ids: undefined as string[] | undefined } })
    rerender({ ids: ['sw-a'] })
    await act(async () => {})
    expect(tones.count).toBe(0)
    rerender({ ids: ['sw-a', 'sw-b'] })
    expect(tones.count).toBe(2)          // one tone, two notes
    rerender({ ids: ['sw-b', 'sw-a'] })   // the same problems again
    expect(tones.count).toBe(2)
    rerender({ ids: ['sw-b'] })            // sw-a was taken ...
    rerender({ ids: ['sw-b', 'sw-a'] })   // ... and came back
    expect(tones.count).toBe(4)
  })

  it('stays quiet when the dashboard has no sound', () => {
    const tones = fakeAudio('running')
    const { rerender, result } = renderHook(({ ids }) => useProblemSound(false, ids), { initialProps: { ids: [] as string[] } })
    rerender({ ids: ['sw-a'] })
    expect(tones.count).toBe(0)
    expect(result.current.blocked).toBe(false)
  })

  it('asks for a click when the browser blocks sound', async () => {
    fakeAudio('suspended')
    const { result } = renderHook(() => useProblemSound(true, []))
    await waitFor(() => expect(result.current.blocked).toBe(true))
  })
})
