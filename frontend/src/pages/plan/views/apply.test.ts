import { describe, expect, it } from 'vitest'
import type { PlanView } from '@/api/planViews'
import { applyView, currentView } from './apply'

const vip: PlanView = { id: 'v1', name: 'VIP', hall: 'main', view: { x: 1, y: 2, w: 3, h: 4 }, layers: 'status', fade: 'status:50', show: 'problems', private: false, saved: '' }

describe('applyView', () => {
  it('sets hall, layers and filter, and drops an open seat', () => {
    const next = applyView(new URLSearchParams('hall=side&seat=A-1&layers=network&edit=1'), vip)
    expect(Object.fromEntries(next)).toEqual({ hall: 'main', layers: 'status', fade: 'status:50', show: 'problems', pv: 'v1', edit: '1' })
  })
  it('goes back to the default layers for a view saved with them', () => {
    const next = applyView(new URLSearchParams('layers=network'), { ...vip, layers: undefined, fade: undefined, show: 'all' })
    expect(next.has('layers')).toBe(false)
    expect(next.has('show')).toBe(false)
  })
})

describe('currentView', () => {
  it('reads the address and rounds the position', () => {
    expect(currentView(new URLSearchParams('layers=status&show=offline'), 'main', { x: 1.234, y: 2, w: 3, h: 4 }, 'Doors', true))
      .toEqual({ name: 'Doors', hall: 'main', show: 'offline', private: true, view: { x: 1.23, y: 2, w: 3, h: 4 }, layers: 'status' })
  })
})
