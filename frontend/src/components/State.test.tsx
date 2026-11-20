import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import en from '@/i18n/en/state.json'
import de from '@/i18n/de-CH/state.json'
import { renderWithApp } from '@/test/render'
import { StateBadge, StateBit } from './State'
import { STATE_TONE, toneColor, toneOf } from './stateTone'

describe('state looks', () => {
  it('gives each state word one tone, and every word a label in both languages', () => {
    expect(toneOf('offline')).toBe('down')
    expect(toneOf('stale')).toBe('warn')
    expect(toneOf('something new')).toBe('off')
    expect(toneColor('off')).toBe('gray')
    for (const word of Object.keys(STATE_TONE)) {
      expect(en).toHaveProperty(word)
      expect(de).toHaveProperty(word)
    }
    expect(Object.values(de).join(' ')).not.toContain('ß')
  })

  it('draws a badge with the word or the page’s own label, and a bit', () => {
    const { container } = renderWithApp(<><StateBadge state="offline" /><StateBadge state="failed" label="3 failed" /><StateBit state="degraded" /></>)
    expect(screen.getByText('Offline').closest('[data-state]')).toHaveAttribute('data-state', 'offline')
    expect(screen.getByText('3 failed')).toBeInTheDocument()
    expect(container.querySelector('.fb-bit.is-warn')).toHaveAttribute('aria-hidden', 'true')
  })
})
