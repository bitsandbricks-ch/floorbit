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
| `kiosk` | The big screen in the hall | Pure black, stronger lines, larger type. Dark only. The default on `/kiosk`. |
| `classic` | People who liked the old look | The previous GitHub-dark surfaces and orange accent. Dark only. |
| `custom` | An event's own look | Accent, background, panel and text colours from settings; the rest is derived. |

Light and dark are a separate switch (the sun/moon button, or the operating system). Presets that
only come in one hide the button.

## One screen, another preset

Add `?theme=<preset>` to any page: `/kiosk?theme=classic` or `/?theme=ops`. The browser keeps it in
a cookie, so the hall projector stays on its preset after a reload while the orga desk uses another
from the same server. `?theme=default` goes back to the site default.

`/kiosk` uses the `kiosk` preset while the site default is `floorbit`. When the site uses `custom`
(or any other preset), the kiosk follows it, so an event's colours reach the big screen too.

## Event name and logo

- **Event name** (`FLOORBIT_EVENT_NAME`): shown in the top bar next to the Floorbit mark and as the
  kiosk heading (the kiosk's `?title=` still wins).
- **Event logo**: SVG, PNG, JPEG or WebP up to 256 KB, uploaded in settings. It replaces the Floorbit
  logo in the top bar and on the kiosk; the powered-by footer stays. It is stored inside `data.json`,
  so a backup carries it and an offline LAN needs no image host. It is served from `/brand/logo`
  with a sandboxing Content-Security-Policy, so an uploaded SVG can't run script.

## Custom colours

Set the accent and, for a full look, the background. Empty fields are derived:

- a dark background makes the theme dark only, a light one light only;
- panels are a shade of the background, text is near white or near black;
- text on accent fills is ink or white, whichever has more contrast.

Settings warns when the accent has less than 3:1 contrast against the background.

## Files

| File | What it holds |
| --- | --- |
| `static/css/brand/tokens.css` | Seeds (`--theme-*`), tokens (`--color-*`, `--heat-*`, `--plan-*`), the light theme, the Geist fonts. |
| `static/css/brand/themes.css` | The presets and the custom derivation. |
| `static/css/brand/legacy-map.css` | Maps the older `--bg-primary`-style names to the tokens. Remove once the page CSS uses `--color-*` directly. |
| `static/css/brand/brand.css` | The logo in the top bar. |
| `static/brand/` | Logos, icons, favicon and link preview image. |
| `static/fonts/` | Geist and Geist Mono (SIL OFL, `OFL.txt`), shipped so a LAN without internet renders them. |
| `floorbit/theme.py` | Which preset and colours a page renders with, the `?theme=` cookie, `/brand/logo`. |
| `templates/_theme_head.html`, `_brand.html` | The `<head>` every page includes, and the top-bar brand. |
