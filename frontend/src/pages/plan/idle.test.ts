import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useIdle } from './idle'

afterEach(() => vi.useRealTimers())

describe('useIdle', () => {
  it('goes idle after the time and wakes with the pointer', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useIdle(3000))
    expect(result.current).toBe(false)
    act(() => { vi.advanceTimersByTime(3000) })
    expect(result.current).toBe(true)
    act(() => { window.dispatchEvent(new Event('pointermove')) })
    expect(result.current).toBe(false)
    act(() => { vi.advanceTimersByTime(2000) })
    expect(result.current).toBe(false)
    act(() => { vi.advanceTimersByTime(1000) })
    expect(result.current).toBe(true)
  })

  it('never goes idle when off', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useIdle(3000, false))
    act(() => { vi.advanceTimersByTime(10_000) })
    expect(result.current).toBe(false)
  })
})
