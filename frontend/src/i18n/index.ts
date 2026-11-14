// Texts per feature in i18n/<lang>/<feature>.json, set up like Hubra's (by Mike) locales,
// so pull requests that add texts to different pages don't edit the same file.
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

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

export const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'de-CH', label: 'Deutsch' },
] as const
export type Lang = (typeof LANGUAGES)[number]['code']

const STORAGE_KEY = 'floorbit-lang'

function saved(): Lang | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return LANGUAGES.some((l) => l.code === v) ? (v as Lang) : null
  } catch {
    return null
  }
}

/** The saved choice, else the browser's first language we have, else English. */
export function initialLang(languages: readonly string[] = navigator.languages ?? []): Lang {
  const choice = saved()
  if (choice) return choice
  for (const l of languages) {
    if (l.toLowerCase().startsWith('de')) return 'de-CH'
    if (l.toLowerCase().startsWith('en')) return 'en'
  }
  return 'en'
}

export function setLang(lang: Lang) {
  try {
    localStorage.setItem(STORAGE_KEY, lang)
  } catch {
    /* private mode: keep it for this visit */
  }
  document.documentElement.lang = lang
  void i18n.changeLanguage(lang)
}

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
