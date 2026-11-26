// Floorbit's Mantine theme: the shared BitsAndBricks theme (@bitsandbricks/ui) with Floorbit's
// accent. The accent and the neutrals come from CSS (styles/bnb.css feeds the --bnb-* tokens from
// Floorbit's own), so presets, light/dark and an admin's colours apply without a rebuild (#1267).
import type { Chip, MantineColorsTuple, VariantColorsResolver } from '@mantine/core'
import { createBnbTheme, variantColorResolver as bnbVariantColorResolver } from '@bitsandbricks/ui'

// A component's theme entry, typed as its .extend() would type it. Calling .extend() imports the
// whole component into the first page whether it shows there or not (issue #1293).
export const themeEntry = <C extends { extend: (input: never) => unknown }>(input: Parameters<C['extend']>[0]) => input

const shades = (name: string) => Array(10).fill(`var(--bnb-${name})`) as unknown as MantineColorsTuple

// Pages still say color="bit", "up", "down" or "trace"; they are the package's accent and states.
const ALIAS: Record<string, string> = { bit: 'accent', up: 'ok', down: 'err', trace: 'info' }

export const variantColorResolver: VariantColorsResolver = (input) => {
  const color = input.color || input.theme.primaryColor
  return bnbVariantColorResolver({ ...input, color: ALIAS[color] ?? color })
}

export const theme = createBnbTheme({
  accent: 'css',
  overrides: {
    variantColorResolver,
    colors: { bit: shades('accent'), up: shades('ok'), down: shades('err'), trace: shades('info') },
    // Floorbit's tighter corners (issue #934).
    radius: { md: 'var(--radius-bit)', lg: 'var(--radius-card)' },
    components: {
      // A checked chip's text follows the fill: dark on Bit Green, never white at 1.6:1.
      Chip: themeEntry<typeof Chip>({
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
