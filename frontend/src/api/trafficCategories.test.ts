import { describe, expect, it } from 'vitest'
import type { Application } from './applications'
import { sharedEntry } from './applicationShare'
import { BUILTIN_CATEGORIES, categoriesFrom, mixParts } from './trafficCategories'

const ESPORTS = { id: 'esports', name: 'Esports', name_de: 'E-Sport', colour: '#dc2626', builtin: false }

describe('traffic categories', () => {
  it('names a category in the language and counts an unknown one as other', () => {
    const cats = categoriesFrom([...BUILTIN_CATEGORIES, ESPORTS], 'de-CH')
    expect(cats.label('esports')).toBe('E-Sport')
    expect(cats.label('gone')).toBe('Anderes')
    expect(categoriesFrom(BUILTIN_CATEGORIES, 'en').label('social')).toBe('Social')
  })

  it('orders a mix like the list and folds unknown ids into other', () => {
    const cats = categoriesFrom([...BUILTIN_CATEGORIES, ESPORTS], 'en')
    const parts = mixParts({ esports: 5, gone: 2, other: 1, gaming: 10, web: 0 }, cats)
    expect(parts.map((p) => [p.id, p.bytes, p.colour])).toEqual([
      ['gaming', 10, '#16a34a'], ['other', 3, '#94a3b8'], ['esports', 5, '#dc2626']])
  })

  it('shares an own category with Floorbit\'s list as other, but keeps it in an export', () => {
    const app = { id: 'example-cup', name: 'Example Cup', kind: 'game', category: 'esports', part_of: null,
      sites: [], ports: [], cidr: ['198.51.100.0/28'], depots: [] } as unknown as Application
    expect(sharedEntry(app, true).category).toBe('other')
    expect(sharedEntry(app).category).toBe('esports')
  })
})
