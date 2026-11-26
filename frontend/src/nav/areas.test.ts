import { describe, expect, it } from 'vitest'
import { AREAS, HUBS, pageIcon } from './sections'

// The sidebar's areas come from one file each (src/nav/areas/); merging them must not hide a clash.
describe('sidebar areas', () => {
  it('give every page its icon in one file only', () => {
    const ids = AREAS.flatMap((a) => Object.keys(a.icons))
    expect(ids.filter((id, i) => ids.indexOf(id) !== i)).toEqual([])
  })

  it('put a page into one row only', () => {
    const hubs = AREAS.flatMap((a) => (a.hub ? [a.hub] : []))
    const tabs = Object.values(HUBS).flat()
    expect(new Set(hubs).size).toBe(hubs.length)
    expect(tabs.filter((id, i) => tabs.indexOf(id) !== i)).toEqual([])
    expect(tabs.filter((id) => id in HUBS)).toEqual([])
  })

  it('give every row and tab an icon of its own', () => {
    const icons = new Set(AREAS.flatMap((a) => Object.keys(a.icons)))
    const missing = [...Object.keys(HUBS), ...Object.values(HUBS).flat()].filter((id) => !icons.has(id))
    expect(missing).toEqual([])
    expect(pageIcon('network')).toBe(AREAS.find((a) => a.hub === 'network')!.icons.network)
  })
})
