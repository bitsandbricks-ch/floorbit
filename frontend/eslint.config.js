import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

// Times are always 24-hour, in English too: every date and time goes through src/lib/time.ts.
const DATES_MESSAGE = 'Format dates and times with src/lib/time.ts (clock, dayClock, dateTime, dateOnly, formatWhen): always 24-hour.'
const DATES = [
  { selector: "CallExpression[callee.property.name=/^toLocale(Time|Date)String$/]", message: DATES_MESSAGE },
  // A Date's toLocaleString; a number's (1,234) passes no options or only a language.
  { selector: "CallExpression[callee.property.name='toLocaleString'][callee.object.type='NewExpression']", message: DATES_MESSAGE },
  { selector: "CallExpression[callee.property.name='toLocaleString'][arguments.1.type='ObjectExpression'][arguments.1.properties.0.key.name=/^(hour|minute|weekday|day|month|year|dateStyle|timeStyle)$/]", message: DATES_MESSAGE },
  { selector: "NewExpression[callee.object.name='Intl'][callee.property.name='DateTimeFormat']", message: DATES_MESSAGE },
]

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: { globals: globals.browser },
    rules: {
      // Plugin data is drawn as text. HTML from the server never goes into the page.
      'no-restricted-syntax': [
        'error',
        { selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']", message: 'Show plugin and API text as text.' },
        {
          selector: "Property[key.name='queryKey'] > ArrayExpression[elements.0.type='Literal']",
          message: 'Use a key from qk (src/api/keys.ts).',
        },
        // One look for every control (src/ui.css, src/theme.ts): never the browser's own list.
        { selector: "JSXOpeningElement[name.name='select']", message: 'Use Select or EntitySelect, not a native <select>.' },
        { selector: "ImportSpecifier[imported.name='NativeSelect']", message: 'Use Select or EntitySelect, not NativeSelect.' },
        // Switches, ports and seats are picked from what Floorbit knows, never typed (EntitySelect).
        {
          selector: "JSXAttribute[name.name='placeholder'][value.value=/^(A-12|D-6|Gi1\\/0\\/\\d+|sw-[a-z]-\\d+)$/]",
          message: 'A switch, port or seat is picked from the real list: use EntitySelect (src/components/EntitySelect.tsx).',
        },
        // Controls are styled once in src/ui.css; a page restyling one makes it look different from the rest.
        { selector: "JSXAttribute[name.name='styles'] > JSXExpressionContainer > ObjectExpression > Property[key.name=/^(dropdown|option|tab|list)$/]",
          message: 'Dropdowns and tabs are styled in src/ui.css, not per page.' },
        ...DATES,
      ],
    },
  },
  {
    // The one place that formats dates and times.
    files: ['src/lib/time.ts'],
    rules: { 'no-restricted-syntax': 'off' },
  },
])
