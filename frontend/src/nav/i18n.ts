// Only the texts the sidebar needs, for the server pages: the whole app's texts stay out of
// the floor plan's download.
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { germanyBundle } from '@/i18n/germany'
import { initialLang } from '@/i18n/lang'

type Texts = Record<string, unknown>
const files = import.meta.glob<Texts>('../i18n/*/{nav,goto,common,database}.json', { eager: true, import: 'default' })

function bundle(lang: string): Texts {
  const out: Texts = {}
  for (const [path, texts] of Object.entries(files)) {
    const m = path.match(/\/i18n\/([^/]+)\/([^/]+)\.json$/)
    if (m && m[1] === lang) out[m[2]] = texts
  }
  return out
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: bundle('en') },
    'de-CH': { translation: bundle('de-CH') },
    de: { translation: germanyBundle(bundle('de-CH')) },
  },
  lng: initialLang(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
  returnNull: false,
})
