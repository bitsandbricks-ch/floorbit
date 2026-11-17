/** A page's code that a browser asks for after Floorbit was updated: the old file names are gone. */
export function isStaleCode(error: unknown): boolean {
  const text = String((error as Error)?.message ?? error)
  return /dynamically imported module|Importing a module script failed|Loading chunk|error loading dynamically/i.test(text)
}
