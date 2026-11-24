// Floorbit's Mantine theme: the shared BitsAndBricks theme (@bitsandbricks/ui) with Floorbit's
// accent. The accent and the neutrals come from CSS (styles/bnb.css feeds the --bnb-* tokens from
// Floorbit's own), so presets, light/dark and an admin's colours apply without a rebuild. The hex
// pair is Bit Green for the few Mantine shades read from the theme; bnb.css wins for the rest.
// TODO(#1267): accent: 'css' once a release has it (bitsandbricks-ch/ui#9).
import { Chip, type MantineColorsTuple, type VariantColorsResolver } from '@mantine/core'
import { createBnbTheme, variantColorResolver as bnbVariantColorResolver } from '@bitsandbricks/ui'

const shades = (name: string) => Array(10).fill(`var(--bnb-${name})`) as unknown as MantineColorsTuple

// Pages still say color="bit", "up", "down" or "trace"; they are the package's accent and states.
const ALIAS: Record<string, string> = { bit: 'accent', up: 'ok', down: 'err', trace: 'info' }

export const variantColorResolver: VariantColorsResolver = (input) => {
  const color = input.color || input.theme.primaryColor
  return bnbVariantColorResolver({ ...input, color: ALIAS[color] ?? color })
}

export const theme = createBnbTheme({
  accent: { light: '#047857', dark: '#2ee59d' },
  overrides: {
    variantColorResolver,
    colors: { bit: shades('accent'), up: shades('ok'), down: shades('err'), trace: shades('info') },
    // Floorbit's tighter corners (issue #934).
    radius: { md: 'var(--radius-bit)', lg: 'var(--radius-card)' },
    components: {
      // A checked chip's text follows the fill: dark on Bit Green, never white at 1.6:1.
      Chip: Chip.extend({
        vars: (_theme, props) => {
          if (props.variant && props.variant !== 'filled') return { root: {} }
          const color = ALIAS[props.color || 'bit'] ?? props.color ?? 'accent'
          if (color === 'accent') return { root: { '--chip-color': 'var(--bnb-on-accent)' } }
          return { root: ['ok', 'err', 'warn', 'info'].includes(color) ? { '--chip-color': 'var(--bnb-on-status)' } : {} }
        },
      }),
    },
  },
})
