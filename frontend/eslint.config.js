import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

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
      ],
    },
  },
])
