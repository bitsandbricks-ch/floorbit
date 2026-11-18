import { describe, expect, it } from 'vitest'
import { editText, parseTyped, parseValue, toValue } from './dateTimeText'

const NOW = new Date(2026, 10, 17, 12, 0)
const at = (s: string) => { const p = parseTyped(s, { hh: 18, mm: 0 }, NOW); return p && toValue(p) }

describe('dateTimeText', () => {
  it('reads what people type, 24-hour, day first', () => {
    expect(at('14.12.2026 18:30')).toBe('2026-12-14T18:30')
    expect(at('14.12.26 9')).toBe('2026-12-14T09:00')
    expect(at('14/12/2026 1830')).toBe('2026-12-14T18:30')
    expect(at('14.12.')).toBe('2026-12-14T18:00')
    expect(at('01.01. 10:00')).toBe('2027-01-01T10:00')   // already past this year
    expect(at('2026-11-20T08:15')).toBe('2026-11-20T08:15')
  })

  it('refuses what is no date', () => {
    expect(at('31.02.2027')).toBeNull()
    expect(at('14.11.2026 25:00')).toBeNull()
    expect(at('tomorrow')).toBeNull()
  })

  it('round-trips the field value', () => {
    expect(editText('2026-11-14T08:05')).toBe('14.11.2026 08:05')
    expect(parseValue('')).toBeNull()
  })
})
