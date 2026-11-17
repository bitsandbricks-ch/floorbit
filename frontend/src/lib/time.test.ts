import { describe, expect, it } from 'vitest'
import { ago, clock } from './time'

describe('time', () => {
  const now = 1_700_000_000_000
  it('says how long ago, in the page language', () => {
    expect(ago(now / 1000 - 10, 'en', now)).toBe('now')
    expect(ago(now / 1000 - 300, 'en', now)).toBe('5 minutes ago')
    expect(ago(now / 1000 - 7200, 'en', now)).toBe('2 hours ago')
    expect(ago(now / 1000 - 300, 'de-CH', now)).toBe('vor 5 Minuten')
    expect(ago(null, 'en', now)).toBe('–')
  })
  it('writes a clock time', () => {
    expect(clock(now / 1000, 'de-CH')).toMatch(/^\d\d:\d\d$/)
  })
})
