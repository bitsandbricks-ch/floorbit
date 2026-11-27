# Themes

Floorbit runs on very different screens: an orga laptop, a dim ops desk, a projector in a bright
hall, and an event that wants its own colours. Every colour is a token, and a theme only changes
tokens. Status colours (up, down, warning, unknown, disabled) are never themable, so a pink event
theme can't make a dead switch look fine.

## Presets

Pick the site default under **Settings > Appearance** (or with `FLOORBIT_THEME`).

| Preset | For | What changes |
| --- | --- | --- |
| `floorbit` | Default everywhere | Seatbit neutrals, Bit Green accent, Trace Cyan for selection. Light and dark. |
| `ops` | The orga desk | Denser type; the accent turns cyan so green on screen only ever means "up". |
| `kiosk` | The big screen in the hall | Pure black, stronger lines, larger type. Dark only. The default on the Kiosk dashboard and the plan's big screen (`/plan?screen=1`). |
| `classic` | People who liked the old look | The previous GitHub-dark surfaces and orange accent. Dark only. |
| `custom` | An event's own look | Accent, background, panel and text colours from settings; the rest is derived. |

Light and dark are a separate switch (the sun/moon button, or the operating system). Presets that
only come in one hide the button.

## One screen, another preset

Add `?theme=<preset>` to any page: `/kiosk?theme=classic` or `/plan?theme=ops`. The browser keeps it in
a cookie, so the hall projector stays on its preset after a reload while the orga desk uses another
from the same server. `?theme=default` goes back to the site default.

The Kiosk dashboard uses the `kiosk` preset while the site default is `floorbit`. When the site uses `custom`
(or any other preset), the kiosk follows it, so an event's colours reach the big screen too.

## Event name and logo

- **Event name** (`FLOORBIT_EVENT_NAME`): shown at the top of the sidebar next to the Floorbit mark and as the
  kiosk heading (the kiosk's `?title=` still wins).
- **Event logo**: SVG, PNG, JPEG or WebP up to 256 KB, uploaded in settings. It replaces the Floorbit
  logo at the top of the sidebar and on the kiosk; the powered-by footer stays. It is stored inside `data.json`,
  so a backup carries it and an offline LAN needs no image host. It is served from `/brand/logo`
  with a sandboxing Content-Security-Policy, so an uploaded SVG can't run script.

## Custom colours

Set the accent and, for a full look, the background. Empty fields are derived:

- a dark background makes the theme dark only, a light one light only;
- panels are a shade of the background, text is near white or near black;
- text on accent fills is ink or white, whichever has more contrast.

Settings warns when the accent has less than 3:1 contrast against the background.

On the React pages, coloured badges and tinted buttons pull their text 20 % towards the page's
text colour, so small labels keep 4.5:1 against their own tint with the built-in colours in both
the light and the dark theme. The pages are checked with axe in the browser (`color-contrast`
included) before a change to colours goes in. The faint text colour (`--bnb-faint`) is for
decoration only; text people need to read, such as help lines and timestamps,
uses the muted colour (`--bnb-muted`), which passes 4.5:1 in both themes.

## Controls

Dropdowns, tabs, inputs, menus and tooltips look the same on every page. Their sizes, radii, popup
shadow and option colours are the `--ui-*` tokens in `tokens.css`; the React pages apply them to
Mantine's controls in `frontend/src/ui.css` and set the defaults (search, check mark on the right,
a short pop-in) in `frontend/src/theme.ts`. A page never restyles a dropdown or a tab itself, and the
React lint refuses a native `<select>` or `NativeSelect`.

A field that names something Floorbit already knows (a switch, a port, a seat, a block, a hall, a
firewall, an agent, a user or a team) is never typed in. It is an `EntitySelect`
(`frontend/src/components/EntitySelect.tsx`), a searchable list filled from
`GET /api/options/<kind>`. Port lists show only free ports unless the field asks for all of them;
taken ports say which seat or cable holds them.

## Files

| File | What it holds |
| --- | --- |
| `static/css/brand/tokens.css` | Seeds (`--theme-*`), tokens (`--bnb-*` under the shared token names, `--heat-*`, `--plan-*`), the light theme, the Geist fonts. |
| `frontend/src/ui.css` | The `--ui-*` tokens applied to Mantine's dropdowns, tabs, inputs, tooltips and modals. |
| `static/css/brand/themes.css` | The presets and the custom derivation. |
| `static/css/brand/brand.css` | The logo in the sidebar and the phone header. |
| `static/brand/` | Logos, icons, favicon and link preview image. |
| `static/fonts/` | Geist and Geist Mono (SIL OFL, `OFL.txt`), shipped so a LAN without internet renders them. |
| `floorbit/theme.py` | Which preset and colours a page renders with, the `?theme=` cookie, `/brand/logo`. |
| `templates/_theme_head.html`, `_brand.html` | The `<head>` every page includes, and the top-bar brand. |
