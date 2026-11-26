// Texts per feature in i18n/<lang>/<feature>.json, set up like Hubra's (by Mike) locales,
// so pull requests that add texts to different pages don't edit the same file.
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { files as englishCore } from './englishCore'
import { germanyBundle } from './germany'
import { initialLang, rememberLang, setLangLoader, type Lang } from './lang'

type Texts = Record<string, unknown>
type Part = 'core' | 'rest'

// English for the pages outside the shell is in the app's first download (the fallback for a text
// that is missing). The shell's pages need the rest, fetched with the shell (allTexts, issue #1293).
// German comes in the same two parts, each its own file, fetched only by those who read German.
function byFeature(files: Record<string, Texts>): Texts {
  const out: Texts = {}
  for (const [path, texts] of Object.entries(files)) {
    const m = path.match(/\/([^/]+)\.json$/)
    if (m) out[m[1]] = texts
  }
  return out
}

async function files(lang: 'en' | 'de-CH', part: Part): Promise<Record<string, Texts>> {
  if (lang === 'en') {
    if (part === 'core') return englishCore
    return (await import('./english')).files
  }
  return (part === 'core' ? await import('./swissCore') : await import('./swiss')).files
}

/** All texts of ``lang`` ('en' or 'de-CH'), by feature. */
export async function loadBundle(lang: 'en' | 'de-CH'): Promise<Texts> {
  return byFeature({ ...(await files(lang, 'core')), ...(await files(lang, 'rest')) })
}

const loaded = new Map<string, Promise<void>>()
// Once the shell's texts were asked for, a language switch fetches them too.
let wantAll = false

function loadPart(lang: Lang, part: Part): Promise<void> {
  const source = lang === 'en' ? 'en' : 'de-CH'
  const key = `${source}:${part}`
  let done = loaded.get(key)
  if (!done) {
    done = files(source, part).then((f) => {
      const texts = byFeature(f)
      if (source === 'en') {
        i18n.addResourceBundle('en', 'translation', texts, true, true)
        return
      }
      i18n.addResourceBundle('de-CH', 'translation', texts, true, true)
      i18n.addResourceBundle('de', 'translation', germanyBundle(texts), true, true)
    })
    loaded.set(key, done)
  }
  return done
}

/** Fetches a language's texts once, before a page shows it: the first part, and the rest too once
 * the shell's pages are open. English stays loaded as the fallback. */
export function loadLang(lang: Lang): Promise<void> {
  const parts = [loadPart(lang, 'core')]
  if (wantAll) parts.push(loadPart('en', 'rest'), loadPart(lang, 'rest'))
  return Promise.all(parts).then(() => undefined)
}

/** Every text in the reader's language: the shell and the pages in it wait for this. */
export function allTexts(): Promise<void> {
  wantAll = true
  return loadLang((i18n.language as Lang | undefined) ?? initialLang())
}
setLangLoader(loadLang)

export { LANGUAGES, initialLang, setLang, type Lang } from './lang'

const lang = initialLang()
document.documentElement.lang = lang
rememberLang(lang)

void i18n.use(initReactI18next).init({
  resources: { en: { translation: byFeature(englishCore) } },
  lng: lang,
  fallbackLng: 'en',
  interpolation: { escapeValue: false }, // React escapes already
  returnNull: false,
})

/** Resolves once the reader's language is there: the app renders after it, so it never flashes English. */
export const i18nReady: Promise<void> = loadLang(lang).then(() => { void i18n.changeLanguage(lang) })

export default i18n
