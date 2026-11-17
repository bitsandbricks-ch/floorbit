import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useLiveEvent } from './live'

class FakeSource {
  static made: FakeSource[] = []
  listeners = new Map<string, Set<(e: MessageEvent) => void>>()
  closed = false
  url: string
  constructor(url: string) { this.url = url; FakeSource.made.push(this) }
  addEventListener(type: string, fn: (e: MessageEvent) => void) { if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type)!.add(fn) }
  removeEventListener(type: string, fn: (e: MessageEvent) => void) { this.listeners.get(type)?.delete(fn) }
  close() { this.closed = true }
  emit(type: string, data: unknown) { this.listeners.get(type)?.forEach((fn) => fn({ data: JSON.stringify({ type, data }) } as MessageEvent)) }
}

describe('live events', () => {
  afterEach(() => { vi.unstubAllGlobals(); FakeSource.made = [] })

  it('shares one stream between every hook and closes it with the last', () => {
    vi.stubGlobal('EventSource', FakeSource)
    const a = vi.fn(), b = vi.fn()
    const one = renderHook(() => useLiveEvent('plan.changed', a))
    const two = renderHook(() => useLiveEvent('cables.changed', b))
    expect(FakeSource.made).toHaveLength(1)
    FakeSource.made[0].emit('cables.changed', { id: 'c1' })
    expect(b).toHaveBeenCalledWith({ id: 'c1' })
    expect(a).not.toHaveBeenCalled()
    one.unmount()
    expect(FakeSource.made[0].closed).toBe(false)
    two.unmount()
    expect(FakeSource.made[0].closed).toBe(true)
  })
})
