// Texts per feature in i18n/<lang>/<feature>.json, set up like Hubra's (by Mike) locales,
// so pull requests that add texts to different pages don't edit the same file.
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { germanyBundle } from './germany'
import { initialLang, rememberLang, setLangLoader, type Lang } from './lang'

type Texts = Record<string, unknown>
// English is in the app's first download: it is the fallback for a text that is missing. German
// (about 70 kB gzipped) is its own file, fetched only by those who read German.
const english = import.meta.glob<Texts>('./en/*.json', { eager: true, import: 'default' })

function byFeature(files: Record<string, Texts>): Texts {
  const out: Texts = {}
  for (const [path, texts] of Object.entries(files)) {
    const m = path.match(/\/([^/]+)\.json$/)
    if (m) out[m[1]] = texts
  }
  return out
}

/** All texts of ``lang`` ('en' or 'de-CH'), by feature. */
export async function loadBundle(lang: 'en' | 'de-CH'): Promise<Texts> {
  if (lang === 'en') return byFeature(english)
  const { files } = await import('./swiss')
  return byFeature(files)
}

let german: Promise<void> | null = null

/** Fetches the German texts once, before a page shows German. */
export function loadLang(lang: Lang): Promise<void> {
  if (lang === 'en') return Promise.resolve()
  german ??= loadBundle('de-CH').then((texts) => {
    i18n.addResourceBundle('de-CH', 'translation', texts, true, true)
    i18n.addResourceBundle('de', 'translation', germanyBundle(texts), true, true)
  })
  return german
}
setLangLoader(loadLang)

export { LANGUAGES, initialLang, setLang, type Lang } from './lang'

const lang = initialLang()
document.documentElement.lang = lang
rememberLang(lang)

void i18n.use(initReactI18next).init({
  resources: { en: { translation: byFeature(english) } },
  lng: lang,
  fallbackLng: 'en',
  interpolation: { escapeValue: false }, // React escapes already
  returnNull: false,
})

/** Resolves once the reader's language is there: the app renders after it, so it never flashes English. */
export const i18nReady: Promise<void> = loadLang(lang).then(() => { void i18n.changeLanguage(lang) })

export default i18n
