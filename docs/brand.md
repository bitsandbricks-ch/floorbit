# Floorbit brand

Floorbit shows a LAN party's network on its floor plan: every switch from NetBox, its live status and ports from LibreNMS, the seat blocks, and which switch port each seat is plugged into. It is Seatbit's sibling from bitsandbricks.ch. Seatbit knows who sits where; Floorbit knows what they are plugged into.

The brand is the same dark hall as Seatbit, seen from the ceiling. Same grid, same green, same type. Floorbit adds one colour of its own, **Trace Cyan**, for the cable you are following.

## Name

- Write **Floorbit** in text: capital F, one word. Never "FloorBit", "Floor Bit" or "floorbit" in a sentence.
- The wordmark is lowercase: **floor** in `color-fg`, **bit** in `color-bit`. Every bitsandbricks product ends in a green "bit"; keep it.
- Tagline: *Your LAN party's network, live on the floor plan.*
- One-liner: *Which switch, which port, which seat.*

## Logo

The mark is Seatbit's 3×3 grid seen from above. The six lit cells are the corner of a hall: the back wall across the top and a row of desks down the side. Together they read as an **F**. The three unlit cells are open floor. Seatbit's lit cells draw a chair from the side; Floorbit's draw the room from above.

| File (`static/brand/`) | Use |
| --- | --- |
| `floorbit-logo.svg` | Horizontal lockup on dark grounds. The default. |
| `floorbit-logo-light.svg` | Lockup on light grounds. |
| `floorbit-mark.svg`, `-light.svg` | Mark alone: phone top bar, avatars, the kiosk corner. |
| `floorbit-mark-mono.svg` | One colour, `currentColor`, no open floor. |
| `floorbit-wordmark*.svg` | Wordmark alone, when the mark is already on screen. |
| `floorbit-icon.svg`, `icon-512.png` | App icon on an ink tile (PWA, Discord bot avatar). |
| `favicon.svg` | Favicon. Drops the open floor so it reads at 16 px. |
| `og-image.svg`, `og-image.png` | 1200×630 link preview. |

- Clear space is one cell width on every side. Minimum size: mark 16 px, lockup 96 px wide.
- Don't recolour single cells, rotate the mark, add outlines or shadows, or set the wordmark in another font. With one colour available, use the mono files.
- The wordmark is outlined Geist Bold at −2.5% tracking, the same construction as Seatbit's, so it needs no font. The brand files live in `static/brand/`; [docs/themes.md](themes.md) covers the theme tokens.
- Event themes put the event's own logo in the top bar. Floorbit then moves to the footer as the powered-by pill; it never sits next to an event logo at the same size.

## Colour

Dark first. Neutrals are Seatbit's exactly, so the two apps feel like one product family when they sit side by side on an orga laptop.

- `color-bit` (Bit Green) is the brand and the action colour: primary buttons, focus, links, the logo. Text on a green fill is `color-on-bit`, never white on the bright green.
- `color-trace` (Trace Cyan) is Floorbit's own: whatever the person is looking at. The selected switch, the box-select marquee, the line from a seat to its port. Never use it for status.
- Status has its own fixed set: `color-up`, `color-down`, `color-warn`, `color-unknown`, `color-disabled`. Themes and events can change the accent and backgrounds, never these, so a pink event theme still can't make a dead switch look fine.
- Every status shows a word or glyph next to its colour (▲ up, ▼ down, ! warn, ? unknown). In the light theme up and down differ by hue only.
- Traffic heat runs `heat-0` to `heat-5`: grey, through cyan, to amber and red. It stays off green so a busy port never looks like "up".
- `color-faint` is for hints only; it is under 4.5:1 in Dark and Classic.

## Typography

- **Geist** for the UI and **Geist Mono** for data. Both SIL OFL; ship the woff2 files with the app so a LAN without internet still renders them.
- Use `mono` for anything people compare letter by letter: seat labels (B12), switch names (sw-b-03), ports (Gi1/0/17), IPs, MACs, traffic numbers. Turn on tabular figures.
- Headings bold or semibold with slight negative tracking; body regular 14 px. Kiosk scales every step up (see Themes).

## Shape and texture

- `radius-bit` (6 px) on seats, chips, inputs and buttons; `radius-card` (14 px) on panels; `radius-pill` on the footer and status pills.
- Seat cells on the plan use 22% of their width as radius, like the logo's cells, so the plan and the mark look made of the same bits.
- The seat-grid pattern (`plan-cell` on `color-ink`) is the background texture behind the floor plan and on the link preview. Keep it barely visible; Kiosk turns it off.

## Footer

Every page ends with the bitsandbricks footer, identical to Seatbit's: an amber **☕ Buy me a coffee** pill (`color-warn` text on a 10% `color-warn` tint, 40% border) linking to buymeacoffee.com/bitsandbricks, and a green **Powered by bitsandbricks.ch** pill (`color-bit` on `color-bit-soft`, 40% border) linking to bitsandbricks.ch. Self-hosters are asked to keep the powered-by pill. The kiosk shows a small powered-by line in a corner instead of the full footer.

## Voice

Like the orga on the radio: short, calm, specific. Name the thing and the number.

- "sw-b-03 is down. 24 seats in Hall B are offline." rather than "A network issue has been detected."
- "Seat B12 · Gi1/0/17 · 940 Mbit/s" rather than "Port statistics for the selected seat".
- English in the UI. No emoji except the coffee cup in the footer.
