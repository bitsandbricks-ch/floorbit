# Crew notice

One short message from a lead to the whole crew, such as "Hall B: power work at 14:00, leave row C
alone". It shows as a banner at the top of every crew page and on the floor plan.

## Put one up

Leads (the `incidents.assign` permission) open the user menu on any of the newer pages and pick
**Crew notice**:

- **Message**: up to 280 characters.
- **Level**: *Info*, or *Warning* for something people must not miss.
- **Show it for**: 1 to 24 hours, or until you take it down.

A new notice replaces the one before. **Take down** removes it for everyone. Closing an event
([past events](events.md)) takes it down too.

## Seeing it

Everyone who can see the floor plan sees the notice. Pages check for a new one every 30 seconds;
the floor plan updates as soon as it changes. Each person can hide the notice with the cross; a new
notice shows again.

Putting a notice up and taking it down are in the [audit log](audit.md), under *incidents*.

With the [crew Discord channel](crew-discord.md) set up, each notice is posted there too, so people
away from Floorbit see it. Turn that off with `DISCORD_CREW_NOTICES=false` or under **Settings >
Crew Discord channel**.

## API

`GET /api/notice` returns `{"notice": {...}}` or `{"notice": null}`. `PUT /api/notice` with
`{"text", "level": "info"|"warn", "hours"}` (`0`: until taken down) puts one up, `DELETE /api/notice`
takes it down. See the [API reference](api-reference.md).
