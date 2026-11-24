import { afterEach, describe, expect, it, vi } from 'vitest'
import { getWidget } from './widgetBatch'

function answer(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

afterEach(() => vi.restoreAllMocks())

describe('getWidget', () => {
  it('sends the tiles asked for together as one request', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(() => answer({
      results: [{ status: 200, body: { type: 'number', value: 1 } }, { status: 404, body: { error: 'No such widget' } }],
    }))
    const a = getWidget('/api/dashboard/floorbit/peak?range=1h')
    const b = getWidget('/api/plugins/demo/widgets/gone')
    await expect(a).resolves.toEqual({ type: 'number', value: 1 })
    await expect(b).rejects.toMatchObject({ status: 404, message: 'No such widget' })
    expect(fetch).toHaveBeenCalledTimes(1)
    const url = String(fetch.mock.calls[0][0])
    expect(url.startsWith('/api/dashboard/widgets?')).toBe(true)
    expect(new URLSearchParams(url.split('?')[1]).getAll('u'))
      .toEqual(['/api/dashboard/floorbit/peak?range=1h', '/api/plugins/demo/widgets/gone'])
  })

  it('asks a lone tile and other addresses directly', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(() => answer({ type: 'number', value: 2 }))
    await expect(getWidget('/api/dashboard/floorbit/seats')).resolves.toEqual({ type: 'number', value: 2 })
    await getWidget('/api/dashboards/abc/public/tiles/seats')
    expect(fetch.mock.calls.map((c) => String(c[0])))
      .toEqual(['/api/dashboard/floorbit/seats', '/api/dashboards/abc/public/tiles/seats'])
  })
})
