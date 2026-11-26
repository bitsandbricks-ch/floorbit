import { describe, expect, it } from 'vitest'
import { gamesFile, rulesFile, shareUrl, type SharedEntry } from './applicationShare'

const arena: SharedEntry = {
  id: 'example-arena', name: 'Example "Arena"', kind: 'game', category: 'gaming', part_of: 'steam',
  sites: ['example.com'], ports: ['udp/7777'], cidr: [], depots: [],
}

describe('sharing an application', () => {
  it('writes the games/ file with quoted values and its source', () => {
    expect(gamesFile(arena, '  seen in our\ncache log ')).toBe([
      'id: "example-arena"', 'name: "Example \\"Arena\\""', 'kind: "game"', 'category: "gaming"', 'part_of: "steam"',
      'sites: ["example.com"]', 'ports: ["udp/7777"]', 'source: "seen in our cache log"', '',
    ].join('\n'))
  })

  it('opens GitHub on a new file in games/', () => {
    const url = new URL(shareUrl(arena, 'x'))
    expect(url.origin + url.pathname).toBe('https://github.com/bitsandbricks-ch/floorbit-plugins/new/main/games')
    expect(url.searchParams.get('filename')).toBe('example-arena.yaml')
    expect(url.searchParams.get('value')).toContain('source: "x"')
  })

  it('exports a rules file, with part_of only on games', () => {
    const doc = JSON.parse(rulesFile([arena, { ...arena, id: 'grp', kind: 'sitegroup' }]))
    expect(doc.version).toBe(1)
    expect(doc.applications.map((a: SharedEntry) => a.part_of)).toEqual(['steam', null])
  })
})
