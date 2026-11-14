import { describe, expect, it } from 'vitest'
import { bundle, initialLang } from './index'

function keys(obj: unknown, prefix = ''): string[] {
  if (typeof obj !== 'object' || obj === null) return [prefix]
  return Object.entries(obj).flatMap(([k, v]) => keys(v, prefix ? `${prefix}.${k}` : k))
}

describe('translations', () => {
  it('has every English text in German too, and nothing extra', () => {
    expect(keys(bundle('de-CH')).sort()).toEqual(keys(bundle('en')).sort())
  })

  it('writes Swiss German: no ß', () => {
    expect(JSON.stringify(bundle('de-CH'))).not.toContain('ß')
  })

  it('picks German for a German browser, English otherwise', () => {
    localStorage.clear()
    expect(initialLang(['de-DE', 'en'])).toBe('de-CH')
    expect(initialLang(['fr-CH', 'en-GB'])).toBe('en')
    expect(initialLang(['fr'])).toBe('en')
  })
})
