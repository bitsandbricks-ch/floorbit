import { render, screen } from '@testing-library/react'
import axe from 'axe-core'
import { describe, expect, it } from 'vitest'
import { DEFAULT_THEME, defaultVariantColorsResolver, mergeMantineTheme } from '@mantine/core'
import { theme as floorbit, variantColorResolver } from '@/theme'
import { StatCard } from './StatCard'

describe('StatCard', () => {
  it('keeps the line under the figure and the trend inside the list (issue #230)', async () => {
    const { container } = render(<StatCard label="Clients" value="254" sub="2.4 GHz: 62" trend={[1, 3, 2]} />)
    expect(screen.getByText('254').tagName).toBe('DD')
    expect(screen.getByText('2.4 GHz: 62').closest('dd')).not.toBeNull()
    const result = await axe.run(container, { runOnly: ['definition-list', 'dlitem'] })
    expect(result.violations).toEqual([])
  })
})

describe('Badge colours', () => {
  const theme = mergeMantineTheme(DEFAULT_THEME, floorbit)
  const resolve = (variant: string, color: string) =>
    variantColorResolver({ variant, color, theme: theme as never, gradient: undefined, autoContrast: false })

  it('pulls light-variant text towards the page text so it passes 4.5:1 on its tint (issue #230)', () => {
    expect(resolve('light', 'warn').color).toBe('color-mix(in srgb, var(--color-warn) 80%, var(--color-fg))')
    expect(resolve('light', 'warn').background).toContain('var(--color-warn) 14%')
  })

  it('uses the muted text colour for grey outlines and dark text on filled cyan', () => {
    expect(resolve('outline', 'gray').color).toBe('var(--color-muted)')
    expect(resolve('filled', 'trace').color).toBe('var(--color-ink)')
    expect(resolve('light', 'gray')).toEqual(defaultVariantColorsResolver({ variant: 'light', color: 'gray', theme: theme as never, autoContrast: false }))
  })
})
