import { describe, expect, it } from 'vitest'
import { files as english } from './english'
import { files as englishCore } from './englishCore'
import { germanyBundle, toGermany } from './germany'
import { initialLang, loadBundle } from './index'
import { files as swiss } from './swiss'
import { files as swissCore } from './swissCore'

function keys(obj: unknown, prefix = ''): string[] {
  if (typeof obj !== 'object' || obj === null) return [prefix]
  return Object.entries(obj).flatMap(([k, v]) => keys(v, prefix ? `${prefix}.${k}` : k))
}

describe('translations', () => {
  it('has every English text in German too, and nothing extra', async () => {
    expect(keys(await loadBundle('de-CH')).sort()).toEqual(keys(await loadBundle('en')).sort())
  })

  it('splits both languages the same way: the first download and the rest, each text file once', () => {
    const names = (files: Record<string, unknown>) => Object.keys(files).map((p) => p.split('/').pop()).sort()
    expect(names(swissCore)).toEqual(names(englishCore))
    expect(names(swiss)).toEqual(names(english))
    expect(names(english).filter((n) => names(englishCore).includes(n))).toEqual([])
    expect(names({ ...english, ...englishCore }).length).toBe(Object.keys(import.meta.glob('./en/*.json')).length)
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
