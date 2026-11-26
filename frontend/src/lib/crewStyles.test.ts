import { afterEach, describe, expect, it } from 'vitest'
import { crewStyles, resetCrewStyles } from './crewStyles'

afterEach(() => {
  document.head.innerHTML = ''
  resetCrewStyles()
})

describe('crewStyles', () => {
  it('puts the full set where the part was, ahead of the app styles', async () => {
    document.head.innerHTML =
      '<link rel="stylesheet" href="/m-part.css" data-mantine="part"><meta name="fb-mantine-full" content="/m-full.css">' +
      '<link rel="stylesheet" href="/app.css">'
    const done = crewStyles()
    const full = document.querySelector<HTMLLinkElement>('link[data-mantine="full"]')!
    expect(full.getAttribute('href')).toBe('/m-full.css')
    full.dispatchEvent(new Event('load'))
    await done
    expect([...document.head.querySelectorAll('link')].map((l) => l.getAttribute('href'))).toEqual(['/m-full.css', '/app.css'])
    expect(crewStyles()).toBe(done)
  })

  it('does nothing on a page that has the full set', async () => {
    document.head.innerHTML = '<link rel="stylesheet" href="/m-full.css" data-mantine="full">'
    await crewStyles()
    expect(document.head.querySelectorAll('link')).toHaveLength(1)
  })
})
