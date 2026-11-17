import { describe, expect, it } from 'vitest'
import { readLayers } from './layers'
import { fromOldMode, isEditing, kioskHref, setEditing } from './workspace'

describe('plan workspace', () => {
  it('opens old mode links on what they showed', () => {
    const read = (s: string) => fromOldMode(new URLSearchParams(s), readLayers(new URLSearchParams(s)))
    expect(read('hall=main')).toBeNull()
    const checkin = read('hall=main&mode=checkin')!
    expect(checkin.has('mode')).toBe(false)
    expect(checkin.get('show')).toBe('checked_in')
    expect(checkin.get('layers')).toBe('grid,marks,checkin')
    expect(read('mode=network&layers=grid')!.get('layers')).toBe('grid')
    expect(isEditing(read('mode=edit&hall=main')!)).toBe(true)
    expect(read('mode=live')!.toString()).toBe('')
  })

  it('takes up the tools and puts them down again', () => {
    const edit = setEditing(new URLSearchParams('hall=main&seat=A-1&view=list&show=problems'), true)
    expect(isEditing(edit)).toBe(true)
    expect(edit.has('seat')).toBe(false)
    expect(edit.has('view')).toBe(false)
    expect(edit.get('show')).toBe('problems')
    expect(isEditing(setEditing(edit, false))).toBe(false)
  })

  it('opens the kiosk on the same hall and layers', () => {
    expect(kioskHref('main', new URLSearchParams('layers=grid,marks&seat=A-1'))).toBe('/plan?screen=1&hall=main&layers=grid%2Cmarks')
  })
})
