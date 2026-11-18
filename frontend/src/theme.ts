// Mantine on top of Floorbit's design tokens (static/css/brand/tokens.css). Colours are CSS
// variables, so presets, light/dark and an admin's custom theme apply to React pages without
// a rebuild. Built after Hubra's (by Mike) packages/ui/src/theme.ts.
import {
  Autocomplete,
  Checkbox,
  Chip,
  Combobox,
  createTheme,
  Menu,
  MultiSelect,
  Popover,
  Radio,
  Select,
  TableScrollContainer,
  Tooltip,
  defaultVariantColorsResolver,
  type CSSVariablesResolver,
  type MantineColorsTuple,
  type VariantColorsResolver,
} from '@mantine/core'

const token = (name: string) => Array(10).fill(`var(--color-${name})`) as unknown as MantineColorsTuple

const TOKENS = ['bit', 'trace', 'up', 'down', 'warn']

export const variantColorResolver: VariantColorsResolver = (input) => {
  const result = defaultVariantColorsResolver(input)
  const color = input.color || input.theme.primaryColor
  if (input.variant === 'filled' && color === 'bit') {
    return { ...result, color: 'var(--color-on-bit)', hover: 'var(--color-bit-hover)' }
  }
  if (input.variant === 'filled' && (color === 'down' || color === 'up' || color === 'warn' || color === 'trace')) {
    return { ...result, color: 'var(--color-ink)' }
  }
  // Mantine can't take alpha off a CSS variable, so "light" became a solid fill in the light theme
  // (dark text on dark green). Mix the token with transparency ourselves.
  if (input.variant === 'light' && TOKENS.includes(color)) {
    const tint = (pct: number) => `color-mix(in srgb, var(--color-${color}) ${pct}%, transparent)`
    // The text is pulled 20 % towards the page's text colour: the tokens alone missed 4.5:1 on their
    // own tint at badge sizes (amber 3.6:1 in the light theme). Darker in light, lighter in dark (issue #230).
    const text = `color-mix(in srgb, var(--color-${color}) 80%, var(--color-fg))`
    return { ...result, background: tint(14), hover: tint(22), color: text, border: 'transparent' }
  }
  // Mantine's grey outline (#868e96) is 3.3:1 on white; use the muted text colour, which passes in both themes.
  if (input.variant === 'outline' && color === 'gray') {
    return { ...result, color: 'var(--color-muted)', border: '1px solid var(--color-line)' }
  }
  return result
}

const POP = { offset: 6, shadow: 'none', transitionProps: { transition: 'pop-top-left' as const, duration: 120 } }

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
  components: {
    // Dropdowns open like an app's menu: a quick pop from where they were opened, a check on the
    // chosen option, never the browser's own list. Their look is in ui.css.
    Select: Select.extend({ defaultProps: { checkIconPosition: 'right', maxDropdownHeight: 320, comboboxProps: POP } }),
    MultiSelect: MultiSelect.extend({ defaultProps: { checkIconPosition: 'right', maxDropdownHeight: 320, comboboxProps: POP } }),
    Autocomplete: Autocomplete.extend({ defaultProps: { maxDropdownHeight: 320, comboboxProps: POP } }),
    Combobox: Combobox.extend({ defaultProps: POP }),
    Menu: Menu.extend({ defaultProps: { ...POP, position: 'bottom-end' } }),
    Popover: Popover.extend({ defaultProps: POP }),
    Tooltip: Tooltip.extend({ defaultProps: { openDelay: 250, transitionProps: { transition: 'fade', duration: 100 } } }),
    // A checked chip's text is white whatever its colour: on Bit Green in the dark theme that was
    // 1.6:1. Use the same text colours as filled buttons and badges (variantColorResolver).
    Chip: Chip.extend({
      vars: (_theme, props) => {
        const color = props.color || 'bit'
        if (props.variant && props.variant !== 'filled') return { root: {} }
        if (color === 'bit') return { root: { '--chip-color': 'var(--color-on-bit)' } }
        return { root: TOKENS.includes(color) ? { '--chip-color': 'var(--color-ink)' } : {} }
      },
    }),
    // The tick and the radio dot are white by default: barely visible on Bit Green in the dark theme.
    Checkbox: Checkbox.extend({
      vars: (_theme, props) => ({ root: !props.color || props.color === 'bit' ? { '--checkbox-icon-color': 'var(--color-on-bit)' } : {} }),
    }),
    Radio: Radio.extend({
      vars: (_theme, props) => ({ root: !props.color || props.color === 'bit' ? { '--radio-icon-color': 'var(--color-on-bit)' } : {} }),
    }),
    // A wide table scrolls sideways on a phone; without focus a keyboard can't scroll it (issue #286).
    TableScrollContainer: TableScrollContainer.extend({
      defaultProps: { scrollAreaProps: { viewportProps: { tabIndex: 0 } } },
    }),
  },
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
