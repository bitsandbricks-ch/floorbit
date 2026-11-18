import { describe, expect, it } from 'vitest'
import { germanyBundle, toGermany } from './germany'
import { initialLang, loadBundle } from './index'

function keys(obj: unknown, prefix = ''): string[] {
  if (typeof obj !== 'object' || obj === null) return [prefix]
  return Object.entries(obj).flatMap(([k, v]) => keys(v, prefix ? `${prefix}.${k}` : k))
}

describe('translations', () => {
  it('has every English text in German too, and nothing extra', async () => {
    expect(keys(await loadBundle('de-CH')).sort()).toEqual(keys(await loadBundle('en')).sort())
  })

  it('writes Swiss German: no ß', async () => {
    expect(JSON.stringify(await loadBundle('de-CH'))).not.toContain('ß')
  })

  it('writes German German with ß, from the same texts', async () => {
    const de = germanyBundle(await loadBundle('de-CH'))
    expect(keys(de).sort()).toEqual(keys(await loadBundle('en')).sort())
    const text = JSON.stringify(de)
    for (const swiss of ['schliessen', 'draussen', 'weiss ', 'Grossbildschirm']) expect(text).not.toContain(swiss)
    expect(toGermany('Fenster schliessen')).toBe('Fenster schließen')
    expect(toGermany('Grosser Bildschirm, grosse Halle')).toBe('Großer Bildschirm, große Halle')
    expect(toGermany('Du weisst es, {{grossName}} weiss es')).toBe('Du weißt es, {{grossName}} weiß es')
    // Words that keep "ss" in Germany too
    expect(toGermany('Passwort, Messwert, Schlüssel, dass, muss, Aussehen, Adresse')).toBe('Passwort, Messwert, Schlüssel, dass, muss, Aussehen, Adresse')
  })

  it('picks German for a German browser, English otherwise', () => {
    localStorage.clear()
    expect(initialLang(['de-CH', 'en'])).toBe('de-CH')
    expect(initialLang(['de', 'en'])).toBe('de-CH')
    expect(initialLang(['de-DE', 'en'])).toBe('de')
    expect(initialLang(['de-AT'])).toBe('de')
    expect(initialLang(['fr-CH', 'en-GB'])).toBe('en')
    expect(initialLang(['fr'])).toBe('en')
  })
})
