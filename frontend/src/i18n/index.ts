// Texts per feature in i18n/<lang>/<feature>.json, set up like Hubra's (by Mike) locales,
// so pull requests that add texts to different pages don't edit the same file.
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { initialLang } from './lang'

type Texts = Record<string, unknown>
const files = import.meta.glob<Texts>('./*/*.json', { eager: true, import: 'default' })

export function bundle(lang: string): Texts {
  const out: Texts = {}
  for (const [path, texts] of Object.entries(files)) {
    const m = path.match(/^\.\/([^/]+)\/([^/]+)\.json$/)
    if (m && m[1] === lang) out[m[2]] = texts
  }
  return out
}

export { LANGUAGES, initialLang, setLang, type Lang } from './lang'

const lang = initialLang()
document.documentElement.lang = lang

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: bundle('en') },
    'de-CH': { translation: bundle('de-CH') },
  },
  lng: lang,
  fallbackLng: 'en',
  interpolation: { escapeValue: false }, // React escapes already
  returnNull: false,
})

export default i18n
