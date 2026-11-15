# Wi-Fi view

`/wifi` (the **Wi-Fi** button on the floor plan) shows each access point's load, how many clients
it has and which channel it is on, drawn on the floor plan. Issue #98.

## What it shows

- **Figures:** clients in all (and per band), access points up, busy access points and channel
  overlaps.
- **The floor plan** with each placed access point and a soft circle around it. Pick a band
  (2.4, 5 or 6 GHz) and what the colour means:
    - **Channel use:** the radio's channel utilization. Green below 50 %, amber up to 70 %, red
      above. A busy radio is slow for everyone on it, however few clients it has.
    - **Clients:** clients on that band. Red at 40 or more.
    - **Channels:** one colour per channel, with the channel number on the AP.
- **Overlaps:** two access points that are up, on the same channel of the same band and near
  each other get a dashed red ring and are listed. "Near" is a rough rule on the plan (30 % of
  its width on 2.4 GHz, 25 % on 5 GHz, 20 % on 6 GHz), because the plan has no scale and no walls.
  Treat it as a hint to check, not a site survey.
- **Every access point** in a table, with each radio's channel, width, clients and load.
  An AP the Wi-Fi plugin knows but the floor plan doesn't is listed as **Not on the plan**.

The page refreshes every 30 seconds. Floorbit asks the plugins at most every 20 seconds, however
many pages are open.

An access point is busy at 70 % channel use or 40 clients.

## Putting access points on the plan

Access points are inventory devices with the role **access-point**, from NetBox or added by hand.
Place them in the editor like switches. The Wi-Fi plugin's AP is matched to the inventory by name
(not case-sensitive), so name them the same in both. With more than one hall, pick the hall at the
top of the page.

## Privacy

Client counts only. Floorbit never asks a controller for its client list for this page, and drops
anything but the counts a plugin sends (client names, MACs). Nothing is stored: the counts are kept
in memory for 20 seconds.

## Sources

- **UniFi** (built in): reads the controller's access points (`stat/device`): each radio's channel,
  width, channel utilization (`cu_total`) and client count. Turn it on under Settings > Plugins with
  a View Only account.
- **Demo data**: nine access points in the demo hall, with a busy stage AP and one overlap.
- Any plugin with `uses: [wifi]` and a `wifi_aps()` method (see [plugins.md](plugins.md)).

<!-- TODO(Mike): Aruba access points. The built-in Aruba plugin talks to AOS-CX switches, which have
no Wi-Fi; Aruba APs need Aruba Central or an Instant/Mobility controller API. Which one runs at
the events? -->

Everyone who can see the floor plan can see this page. Settings > Features has a `wifi` switch.

## API

`GET /api/wifi?hall=`: `aps` (each with `radios`, `busy`, `on_plan` and plan coordinates `px` and
`py`), `clients`, `up`, `down`, `busy`, `overlaps`, `bands`, `sources`, `errors`, `thresholds`, and
the hall's `drawing`.
