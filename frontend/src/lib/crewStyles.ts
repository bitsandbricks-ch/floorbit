// The pages outside the app shell get only part of Mantine's styles (floorbit/spa.py, issue
// #1293). Before a page inside the shell shows up there (a link from a public page, the "not
// allowed" page, a big-screen dashboard), the full set takes the part's place, so the styles come
// in the same order as when Flask sends them.
let ready: Promise<void> | null = null

export function crewStyles(): Promise<void> {
  if (ready) return ready
  const full = document.querySelector<HTMLMetaElement>('meta[name="fb-mantine-full"]')?.content
  const part = document.querySelector<HTMLLinkElement>('link[data-mantine="part"]')
  if (!full || !part) return (ready = Promise.resolve())
  ready = new Promise((resolve) => {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = full
    link.dataset.mantine = 'full'
    // Not found: show the page anyway, with the styles it has.
    link.onload = link.onerror = () => {
      part.remove()
      resolve()
    }
    part.before(link)
  })
  return ready
}

/** For tests. */
export function resetCrewStyles() {
  ready = null
}
