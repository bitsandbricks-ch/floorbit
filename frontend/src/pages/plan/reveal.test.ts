import { describe, expect, it } from 'vitest'
import { revealActive } from './reveal'

function row(left: number, right: number, activeLeft: number, activeRight: number) {
  const el = document.createElement('div')
  const item = document.createElement('label')
  item.setAttribute('data-active', 'true')
  el.appendChild(item)
  el.getBoundingClientRect = () => ({ left, right }) as DOMRect
  item.getBoundingClientRect = () => ({ left: activeLeft, right: activeRight }) as DOMRect
  el.scrollLeft = 0
  return el
}

describe('revealActive', () => {
  it('scrolls an active item past the right edge into view', () => {
    const el = row(16, 359, 300, 450)
    revealActive(el)
    expect(el.scrollLeft).toBe(450 - 359 + 8)
  })

  it('leaves the row alone when the active item is already in view, or there is none', () => {
    const el = row(16, 359, 20, 100)
    revealActive(el)
    expect(el.scrollLeft).toBe(0)
    expect(() => revealActive(null)).not.toThrow()
  })
})
