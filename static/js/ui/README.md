# Shared controls for the Jinja pages

Plain scripts (no build step) that give the older pages the same dropdowns and tabs as the React
pages (`frontend/src/components/ui.tsx`, `EntitySelect.tsx`). Styles are in `static/css/ui.css` and read the `--ui-*` brand
tokens from `static/css/brand/tokens.css`.

| File | What it does |
| --- | --- |
| `select.js` | Upgrades every `<select>` into a dropdown with a styled list, keyboard support, a search field for long lists, groups and hints. The native select stays the source of truth: `.value`, `change` and `<label for>` keep working. Opt out with `data-native`. `UI.fillSelect()` fills one from an `/api/options` answer. |
| `tabs.js` | Tab strips (`.ui-tabs` or `role="tablist"`) get an underline that slides to the active tab, and arrow keys. The page still decides which tab is active. |

Load them before the page's own scripts. The pages move to React one at a time; these go away with
the last Jinja page.
