// The language choice on its own, without the texts: the sidebar on the server pages
// (src/nav/entry.tsx) needs it but loads only its own few texts.
import i18n from 'i18next'

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
