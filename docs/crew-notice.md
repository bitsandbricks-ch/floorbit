# Crew notice

One short message from a lead to the whole crew, such as "Hall B: power work at 14:00, leave row C
alone". It shows as a badge in the top bar of every crew page (an icon on a phone) and on the floor
plan. Click the badge for the whole message, who put it up and until when.

## Put one up

Leads (the `incidents.assign` permission) open the user menu and pick **Crew notice**, or click the
badge and pick **Change**:

- **Message**: up to 280 characters.
- **Level**: *Info*, or *Warning* for something people must not miss.
- **Show it for**: 1 to 24 hours, or until you take it down.

A new notice replaces the one before. **Take down** (in the badge or the form) removes it for everyone. Closing an event
([past events](events.md)) takes it down too.

## Seeing it

Everyone who can see the floor plan sees the notice. Pages check for a new one every 30 seconds;
the floor plan updates as soon as it changes. The badge is coloured by the level (cyan for info,
yellow for a warning) until you pick **Mark as read**; then it stays in the top bar without colour.
A new notice lights it again. Being read is kept per browser.

Putting a notice up and taking it down are in the [audit log](audit.md), under *incidents*.

With the [crew Discord channel](crew-discord.md) set up, each notice is posted there too, so people
away from Floorbit see it. Turn that off with `DISCORD_CREW_NOTICES=false` or under **Settings >
Crew Discord channel**.

## API

`GET /api/notice` returns `{"notice": {...}}` or `{"notice": null}`. `PUT /api/notice` with
`{"text", "level": "info"|"warn", "hours"}` (`0`: until taken down) puts one up, `DELETE /api/notice`
takes it down. See the [API reference](api-reference.md).
