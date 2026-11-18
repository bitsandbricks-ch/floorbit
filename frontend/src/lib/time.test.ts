import { describe, expect, it } from 'vitest'
import { ago, clock, clockSeconds, dateOnly, dateTime, dayClock, formatWhen } from './time'

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
  it('is 24-hour in English too, never AM or PM', () => {
    // Local dates, so the hours are what the runner's own clock shows.
    const late = new Date(2026, 10, 16, 23, 16, 9)
    const early = new Date(2026, 10, 17, 0, 5, 0)
    for (const lang of ['en', 'en-US', 'de-CH']) {
      expect(clock(late, lang)).toBe('23:16')
      expect(clock(early, lang)).toBe('00:05')
      expect(clockSeconds(late, lang)).toBe('23:16:09')
      expect(dayClock(late, lang)).toMatch(/23:16$/)
      expect(dateTime(late, lang)).toMatch(/23:16$/)
      expect(dateTime(late, lang, true)).toMatch(/23:16:09$/)
      expect(formatWhen(late, { hour: 'numeric' }, lang)).not.toMatch(/AM|PM/)
    }
    expect(clock(late.getTime() / 1000, 'en')).toBe('23:16')   // seconds, as the API sends them
  })
  it('leaves dates without a time alone', () => {
    const d = new Date(2026, 10, 16, 23, 16)
    expect(dateOnly(d, 'de-CH')).toBe('16.11.26')
    expect(dateOnly(d, 'en', { weekday: 'long', day: 'numeric', month: 'long' })).toBe('Monday, 16 November')
  })
  it('puts the day first in English too', () => {
    const d = new Date(2026, 10, 18, 14, 5)
    expect(dateOnly(d, 'en')).toBe('18.11.2026')
    expect(dateTime(d, 'en')).toBe('18.11.2026, 14:05')
    expect(dateOnly(d, 'en-US')).toBe('11/18/26')   // only the app's own English changes
  })
})
