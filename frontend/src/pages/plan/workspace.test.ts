import { describe, expect, it } from 'vitest'
import { readLayers } from './layers'
import { kioskHref, readMode, switchMode } from './workspace'

describe('plan workspace modes', () => {
  it('reads the mode from the address, live by default', () => {
    expect(readMode(new URLSearchParams(''))).toBe('live')
    expect(readMode(new URLSearchParams('mode=network'))).toBe('network')
    expect(readMode(new URLSearchParams('mode=nope'))).toBe('live')
  })

  it('switches layers and the filter with the mode', () => {
    const start = new URLSearchParams('hall=main')
    const checkin = switchMode(start, 'checkin', readLayers(start))
    expect(checkin.get('mode')).toBe('checkin')
    expect(checkin.get('show')).toBe('checked_in')
    expect(checkin.get('layers')).toBe('grid,marks,checkin')
    const live = switchMode(checkin, 'live', readLayers(checkin))
    expect(live.has('mode')).toBe(false)
    expect(live.has('show')).toBe(false)
    expect(live.get('hall')).toBe('main')
  })

  it('drops the live panels when switching to edit', () => {
    const start = new URLSearchParams('hall=main&seat=A-1&view=list')
    const edit = switchMode(start, 'edit', readLayers(start))
    expect(edit.get('mode')).toBe('edit')
    expect(edit.has('seat')).toBe(false)
    expect(edit.has('view')).toBe(false)
  })

  it('opens the kiosk on the same hall and layers', () => {
    expect(kioskHref('main', new URLSearchParams('layers=grid,marks&seat=A-1'))).toBe('/plan?screen=1&hall=main&layers=grid%2Cmarks')
  })
})
