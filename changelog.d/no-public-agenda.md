### Removed

- The public agenda is gone: `/agenda`, its big-screen layout, `/agenda.json` and the calendar feed
  `/agenda.ics`, with the **Schedule and countdown** setting (`SCHEDULE_PAGE`). The schedule stays for
  the crew on `/schedule`, and the shift handover still lists what starts next.
- The Discord bot is for the crew only. Attendees can no longer report a seat with `/report`, and
  `/status` now needs a linked account that works incidents. Floorbit no longer posts to channels
  attendees read: the **Attendee status channel webhook** (`DISCORD_STATUS_WEBHOOK_URL`), the
  **Attendee programme channel webhook** (`DISCORD_SCHEDULE_WEBHOOK_URL`) and
  `SCHEDULE_ANNOUNCE_MINUTES` are gone. Alerts, the crew channel and the crew's slash commands work
  as before. Attendees report a problem with the QR code on their seat.
- An upgrade step removes the saved settings of all of these.
