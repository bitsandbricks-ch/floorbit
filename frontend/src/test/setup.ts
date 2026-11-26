// From Hubra (by Mike): app/frontend/src/test/setup.ts.
import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(cleanup)

// What Mantine needs from a browser that jsdom does not have.
// jsdom has no screen: tests see a computer (min-width queries match), so the shared components
// draw their computer layout (the FilterBar's filters in a row, not behind a phone's button).
// A test of the phone layout stubs matchMedia itself.
window.matchMedia ??= (query: string) =>
  ({
    matches: /\(min-width/.test(query),
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

// German is fetched on first use in the app; tests that switch to it expect it at once.
const { loadLang } = await import('@/i18n')
await loadLang('de-CH')
