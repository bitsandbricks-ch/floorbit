// The language choice on its own, without the texts: the sidebar on the server pages
// (src/nav/entry.tsx) needs it but loads only its own few texts.
import i18n from 'i18next'

export const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'de-CH', label: 'Deutsch (Schweiz)' },
  { code: 'de', label: 'Deutsch (Deutschland, Österreich)' },
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

// The server draws the floor plan's sidebar before any script (templates/_nav.html): it reads the
// language from this cookie, so the first paint is already in the right one.
const COOKIE = 'floorbit_lang'

export function rememberLang(lang: Lang) {
  try {
    document.cookie = `${COOKIE}=${lang}; path=/; max-age=31536000; samesite=lax`
  } catch {
    /* no cookies: the sidebar starts in the browser's language */
  }
}

/** The saved choice, else the browser's first language we have, else English. */
export function initialLang(languages: readonly string[] = navigator.languages ?? []): Lang {
  const choice = saved()
  if (choice) return choice
  for (const l of languages) {
    const code = l.toLowerCase()
    // Switzerland and Liechtenstein write "ss"; a bare "de" is most likely a Swiss crew laptop too.
    if (code === 'de' || code === 'de-ch' || code === 'de-li') return 'de-CH'
    if (code.startsWith('de')) return 'de'
    if (l.toLowerCase().startsWith('en')) return 'en'
  }
  return 'en'
}

// The app's i18n fetches German on first use; the server pages' sidebar has its few texts already.
let loadLang: (lang: Lang) => Promise<void> = () => Promise.resolve()
export function setLangLoader(load: (lang: Lang) => Promise<void>) {
  loadLang = load
}

export function setLang(lang: Lang) {
  try {
    localStorage.setItem(STORAGE_KEY, lang)
  } catch {
    /* private mode: keep it for this visit */
  }
  rememberLang(lang)
  document.documentElement.lang = lang
  void loadLang(lang).then(() => i18n.changeLanguage(lang))
}
