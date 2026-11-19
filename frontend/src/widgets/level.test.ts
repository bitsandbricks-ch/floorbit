import { describe, expect, it } from 'vitest'
import { pickLevel, rowsThatFit } from './level'

describe('pickLevel', () => {
  it('grows with the box', () => {
    expect(pickLevel('table', 200, 100)).toBe('s')
    expect(pickLevel('table', 320, 160)).toBe('m')
    expect(pickLevel('table', 900, 400)).toBe('l')
  })
  it('needs both width and height', () => {
    expect(pickLevel('graph', 1200, 100)).toBe('s')
    expect(pickLevel('graph', 1200, 200)).toBe('m')
  })
  it('keeps a pinned level whatever the box', () => {
    expect(pickLevel('stat', 50, 50, 'l')).toBe('l')
    expect(pickLevel('stat', 2000, 2000, 's')).toBe('s')
  })
  it('counts rows that fit, at least one', () => {
    expect(rowsThatFit(280)).toBe(10)
    expect(rowsThatFit(280, 28)).toBe(9)
    expect(rowsThatFit(10)).toBe(1)
  })
})
