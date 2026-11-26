// From Hubra (by Mike): app/frontend/src/test/setup.ts.
import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(cleanup)

// What Mantine needs from a browser that jsdom does not have.
window.matchMedia ??= (query: string) =>
  ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }) as MediaQueryList

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Element.prototype.scrollIntoView ??= () => {}

// Textarea autosize listens for web fonts loading.
if (!('fonts' in document)) {
  Object.defineProperty(document, 'fonts', {
    value: { addEventListener: () => {}, removeEventListener: () => {}, ready: Promise.resolve() },
  })
}

// German, and the texts of the shell's pages, are fetched on first use in the app; tests render
// pages directly and switch languages, so they expect all of it at once.
const { allTexts, loadLang } = await import('@/i18n')
await allTexts()
await loadLang('de-CH')
