import { afterEach, describe, expect, it } from 'vitest'
import { readServerPage } from './serverPage'

function boot(text: string) {
  const el = document.createElement('script')
  el.type = 'application/json'
  el.id = 'fb-page'
  el.textContent = text
  document.body.append(el)
}

describe('readServerPage', () => {
  afterEach(() => document.getElementById('fb-page')?.remove())

  it('reads "not found" and "not allowed"', () => {
    boot('{"kind":"not-found"}')
    expect(readServerPage()).toEqual({ kind: 'not-found' })
    document.getElementById('fb-page')?.remove()
    boot('{"kind":"forbidden","permission":"seats.edit","role":"Tech"}')
    expect(readServerPage()).toEqual({ kind: 'forbidden', permission: 'seats.edit', role: 'Tech' })
  })

  it('draws the route as usual without one, or with a broken one', () => {
    expect(readServerPage()).toBeNull()
    boot('{not json')
    expect(readServerPage()).toBeNull()
  })
})
