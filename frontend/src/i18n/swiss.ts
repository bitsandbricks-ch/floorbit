// All Swiss German texts in one module, so the app fetches them as one file (see index.ts).
type Texts = Record<string, unknown>
export const files = import.meta.glob<Texts>('./de-CH/*.json', { eager: true, import: 'default' })
