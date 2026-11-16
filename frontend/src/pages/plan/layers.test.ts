import { describe, expect, it } from 'vitest'
import { DEFAULT_LAYERS, PRESETS, presetOf, readLayers, writeLayers } from './layers'

const read = (q: string) => readLayers(new URLSearchParams(q))

describe('floor plan layers in the URL', () => {
  it('starts with what the page always showed', () => {
    expect([...read('').on].sort()).toEqual([...DEFAULT_LAYERS].sort())
  })

  it('keeps old one-layer links working', () => {
    const s = read('traffic=1&power=1&firewalls=1')
    expect(['status', 'electrical', 'firewalls'].every((l) => s.on.has(l as never))).toBe(true)
  })

  it('reads layers and fades, and ignores what it does not know', () => {
    const s = read('layers=network,wifi,attic&fade=wifi:40,network:5,electrical:150,nope:50')
    expect([...s.on]).toEqual(['network', 'wifi'])
    expect(s.fade).toEqual({ wifi: 0.4 })
  })

  it('writes a short, stable address and drops the old switches', () => {
    const next = writeLayers(new URLSearchParams('hall=h1&traffic=1'), { on: new Set(['wifi', 'marks', 'network']), fade: { wifi: 0.5 } })
    expect(next.toString()).toBe('hall=h1&layers=marks%2Cnetwork%2Cwifi&fade=wifi%3A50')
    expect(writeLayers(new URLSearchParams('hall=h1'), { on: new Set(DEFAULT_LAYERS), fade: {} }).toString()).toBe('hall=h1')
  })

  it('names the preset a choice matches', () => {
    expect(presetOf(new Set(PRESETS.electrical))).toBe('electrical')
    expect(presetOf(new Set(['marks', 'wifi']))).toBeNull()
  })
})
