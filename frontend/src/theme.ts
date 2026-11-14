// Mantine on top of Floorbit's design tokens (static/css/brand/tokens.css). Colours are CSS
// variables, so presets, light/dark and an admin's custom theme apply to React pages without
// a rebuild. Built after Hubra's (by Mike) packages/ui/src/theme.ts.
import {
  createTheme,
  defaultVariantColorsResolver,
  type CSSVariablesResolver,
  type MantineColorsTuple,
  type VariantColorsResolver,
} from '@mantine/core'

const token = (name: string) => Array(10).fill(`var(--color-${name})`) as unknown as MantineColorsTuple

const TOKENS = ['bit', 'trace', 'up', 'down', 'warn']

const variantColorResolver: VariantColorsResolver = (input) => {
  const result = defaultVariantColorsResolver(input)
  const color = input.color || input.theme.primaryColor
  if (input.variant === 'filled' && color === 'bit') {
    return { ...result, color: 'var(--color-on-bit)', hover: 'var(--color-bit-hover)' }
  }
  if (input.variant === 'filled' && (color === 'down' || color === 'up' || color === 'warn')) {
    return { ...result, color: 'var(--color-ink)' }
  }
  // Mantine can't take alpha off a CSS variable, so "light" became a solid fill in the light theme
  // (dark text on dark green). Mix the token with transparency ourselves.
  if (input.variant === 'light' && TOKENS.includes(color)) {
    const tint = (pct: number) => `color-mix(in srgb, var(--color-${color}) ${pct}%, transparent)`
    return { ...result, background: tint(14), hover: tint(22), color: `var(--color-${color})`, border: 'transparent' }
  }
  return result
}

export const theme = createTheme({
  primaryColor: 'bit',
  primaryShade: 6,
  autoContrast: false,
  variantColorResolver,
  fontFamily: 'var(--font-sans)',
  fontFamilyMonospace: 'var(--font-mono)',
  headings: { fontFamily: 'var(--font-sans)', fontWeight: '650' },
  defaultRadius: 'md',
  colors: {
    bit: token('bit'),
    trace: token('trace'),
    up: token('up'),
    down: token('down'),
    warn: token('warn'),
  },
  radius: { md: 'var(--radius-bit)', lg: 'var(--radius-card)' },
})

const shared = {
  '--mantine-color-body': 'var(--color-ink)',
  '--mantine-color-text': 'var(--color-fg)',
  '--mantine-color-dimmed': 'var(--color-muted)',
  '--mantine-color-placeholder': 'var(--color-faint)',
  '--mantine-color-anchor': 'var(--color-bit)',
  '--mantine-color-default': 'var(--color-surface)',
  '--mantine-color-default-hover': 'var(--color-raised)',
  '--mantine-color-default-color': 'var(--color-fg)',
  '--mantine-color-default-border': 'var(--color-line)',
  '--mantine-color-error': 'var(--color-down)',
}

export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {},
  light: shared,
  dark: shared,
})
