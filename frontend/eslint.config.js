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

// Pieces that moved to the shared packages (#1266, #1274): their old Floorbit paths are gone, and
// a copy that comes back would drift from the one every app shares.
const SHARED_UI = 'ConfirmButton|DataTable|FilterBar|HoverTimeChart|Markdown|PageError|PageHead|PageTabs|SidePanel|StatTile|State|stateTone|toast|topbarSlot|useFilters|panel|ui'
const SHARED_WIDGETS = 'Sparkline|TimeChart|TileCard|FitWidget|WidgetBody|kinds/.*|level|levelReport|spark|useBox|views|drill|autoPage'
const SHARED = [
  { regex: `^(@/|(\\.\\.?/)+)components/(${SHARED_UI})$`, message: 'This moved to @bitsandbricks/ui: import it from there.' },
  { regex: `^(@/|(\\.\\.?/)+)widgets/(${SHARED_WIDGETS})$`, message: 'This moved to @bitsandbricks/widgets: import it from there.' },
  { regex: '^(@/|(\\.\\.?/)+)lib/staleCode$', message: 'Use isStaleCode from @bitsandbricks/ui.' },
  { regex: '^(@/|(\\.\\.?/)+)(styles/goto|components/notifications/Notifications)\\.css$', message: 'The shared CommandPalette and NotificationsPanel bring their own styles.' },
]
// Inside src/components a sibling import is "./DataTable"; elsewhere "./SidePanel" is the plan's own.
const SHARED_SIBLINGS = { regex: `^\\./(${SHARED_UI})$`, message: 'This moved to @bitsandbricks/ui: import it from there.' }

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
        // A component's .extend() imports all of it into the first page (issue #1293): themeEntry in src/theme.ts.
        {
          selector: "CallExpression[callee.property.name='extend'][callee.object.name=/^[A-Z]/]",
          message: 'Use themeEntry<typeof X>({...}) from src/theme.ts; X.extend() loads the whole component.',
        },
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
        // The browser's dialogs block the page and can't be themed or translated: ConfirmButton asks instead.
        { selector: "CallExpression[callee.object.name='window'][callee.property.name=/^(confirm|alert|prompt)$/]",
          message: 'Ask with ConfirmButton or ConfirmIcon (@bitsandbricks/ui), not the browser dialog.' },
        { selector: "CallExpression[callee.name=/^(confirm|alert|prompt)$/]",
          message: 'Ask with ConfirmButton or ConfirmIcon (@bitsandbricks/ui), not the browser dialog.' },
        // Dates and times go through DateTimeInput: the browser's inputs show AM/PM to English browsers.
        { selector: "JSXAttribute[name.name='type'][value.value=/^(datetime-local|time|date)$/]",
          message: 'Use DateTimeInput (src/components/DateTimeInput.tsx) for dates and times.' },
        ...DATES,
      ],
      'no-restricted-imports': ['error', { patterns: SHARED }],
    },
  },
  {
    files: ['src/components/*.{ts,tsx}'],
    rules: { 'no-restricted-imports': ['error', { patterns: [...SHARED, SHARED_SIBLINGS] }] },
  },
  {
    // The one place that formats dates and times.
    files: ['src/lib/time.ts'],
    rules: { 'no-restricted-syntax': 'off' },
  },
])
