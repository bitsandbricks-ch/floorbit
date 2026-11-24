import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { qk } from './keys'
import { GATHER_MS, PROBLEM_EVENTS, PROBLEMS_EVERY_MS, useLiveRefresh } from './liveRefresh'
import { noticeRecheck } from './queries'

class FakeSource {
  static made: FakeSource[] = []
  listeners = new Map<string, Set<(e: MessageEvent) => void>>()
  readyState = 1
  url: string
  constructor(url: string) { this.url = url; FakeSource.made.push(this) }
  addEventListener(type: string, fn: (e: MessageEvent) => void) { if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type)!.add(fn) }
  removeEventListener(type: string, fn: (e: MessageEvent) => void) { this.listeners.get(type)?.delete(fn) }
  close() { this.readyState = 2 }
  emit(type: string, data: unknown) { this.listeners.get(type)?.forEach((fn) => fn({ data: JSON.stringify({ type, data }) } as MessageEvent)) }
}

function setup() {
  vi.useFakeTimers()
  vi.stubGlobal('EventSource', FakeSource)
  const client = new QueryClient()
  const invalidate = vi.spyOn(client, 'invalidateQueries').mockResolvedValue(undefined)
  const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children)
  const hook = renderHook(() => useLiveRefresh(), { wrapper })
  const keys = () => invalidate.mock.calls.map((c) => c[0]?.queryKey)
  return { hook, source: FakeSource.made[0], keys }
}

describe('live refresh', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); FakeSource.made = [] })

  it('reads the problems once for a burst of events, on one shared stream', () => {
    const { hook, source, keys } = setup()
    expect(FakeSource.made).toHaveLength(1)
    for (const type of PROBLEM_EVENTS) source.emit(type, {})
    expect(keys()).toEqual([])
    vi.advanceTimersByTime(GATHER_MS)
    expect(keys()).toEqual([qk.problems])
    hook.unmount()
  })

  it('a status poll counts only when a switch changed', () => {
    const { hook, source, keys } = setup()
    source.emit('monitor.poll', { changes: [], counts: {} })
    vi.advanceTimersByTime(GATHER_MS)
    expect(keys()).toEqual([])
    source.emit('monitor.poll', { changes: [{ switch_id: 's1' }], counts: {} })
    vi.advanceTimersByTime(GATHER_MS)
    expect(keys()).toEqual([qk.problems])
    hook.unmount()
  })

  it('a new or cleared notice reads the notice again at once', () => {
    const { hook, source, keys } = setup()
    source.emit('notice.changed', { notice: null })
    expect(keys()).toEqual([qk.notice])
    hook.unmount()
  })

  it('nothing runs after the page is gone', () => {
    const { hook, source, keys } = setup()
    source.emit('alerts.changed', {})
    hook.unmount()
    vi.advanceTimersByTime(GATHER_MS)
    expect(keys()).toEqual([])
  })
})

describe('notice recheck', () => {
  const notice = (until: number | null) => ({ text: 'x', level: 'info' as const, until, by: null, at: 0 })

  it('reads again in five minutes, or just after the notice runs out', () => {
    expect(noticeRecheck(null)).toBe(300_000)
    expect(noticeRecheck(notice(null))).toBe(300_000)
    expect(noticeRecheck(notice(1000), 960_000)).toBe(41_000)
    expect(noticeRecheck(notice(10_000), 0)).toBe(300_000)
    expect(noticeRecheck(notice(5), 999_000)).toBe(1000)
  })
})

describe('safety net', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); FakeSource.made = [] })

  it('reads the problems once a minute, not while the tab is hidden', () => {
    const { hook, keys } = setup()
    vi.advanceTimersByTime(PROBLEMS_EVERY_MS + GATHER_MS)
    expect(keys()).toEqual([qk.problems])
    const hidden = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    vi.advanceTimersByTime(PROBLEMS_EVERY_MS + GATHER_MS)
    expect(keys()).toEqual([qk.problems])
    hidden.mockRestore()
    hook.unmount()
  })
})
