# Crew Discord channel

Floorbit can post every incident in the crew's Discord channel. Each incident gets one message and
a thread under it, and both stay in sync with the incident until it is fixed. Crew members whose
Discord account is linked can take an incident or mark it fixed with a button in Discord. The code
is in `integrations/crew.py` and `floorbit/blueprints/crew.py` (issue #32).

## What it does

- **New incident:** a message with what is wrong, where (seat, switch or circuit), the team, the
  status and, on a [match seat](tournament.md), the zone. A thread opens under it, named after the
  place and the title. The first note goes into the thread.
- **Changes:** the message is edited to show the new status and who has the incident. The thread gets
  one line per change: someone took it, it was sent to a tech ([dispatch](dispatch.md)), it is back
  on the board, it was fixed or reopened. Each new note is posted there too.
- **Waiting:** when nobody has taken an incident for 10 minutes (`DISCORD_CREW_WAITING_MINUTES`),
  its thread gets one line, "⏳ Waiting 10 min. Nobody has taken it yet.", the same rule as the
  board's "Waiting" badge. Set `DISCORD_CREW_WAITING_ROLE` to a role ID, for example the leads, and
  that line pings the role. It is said once per incident, also when it is reopened later. Floorbit
  looks once a minute.
- **Not seen:** when a job [sent to a tech](dispatch.md) is still not seen 5 minutes later
  (`DISCORD_CREW_UNSEEN_MINUTES`), its thread gets one line, "📵 Sent to kim 5 min ago, not seen
  yet.", the same rule as the board. It pings nobody. Sent again, it can say so again.
- **Works again:** when the attendee taps "It works again" on the seat's [help page](incidents.md#the-helpdesk-on-each-seat),
  the thread gets "👍 The seat says it works again. Check or ask before marking it fixed." and no
  waiting nudge follows. The incident stays open until someone marks it fixed.
- **Fixed:** the buttons go away and the thread is archived. When the incident is reopened, the
  thread opens again.
- **Buttons:** "Take it" and "Fixed" act as the Floorbit account linked to whoever clicks. That account
  needs the same permission as on the incident board. Only the person who clicked sees the answer.
  Discord users with no linked account are told how to link one, and nothing changes. "Open in
  Floorbit" links to the board when `PUBLIC_URL` is set.
- **Alerts:** without a webhook URL, the switch, health, security and power alerts
  ([integrations.md](integrations.md#discord-alerts)) go to the crew channel through the bot.
  With a webhook URL set, they still go to the webhook. You can use one channel for
  incidents and another for alerts.
- **Mute from the alert:** when a switch-offline or service-down alert comes through the bot and the
  buttons are set up, it has a "Mute sw-a-01 for 1 h" button per switch or red service (up to five;
  a grouped big-outage message has none). It mutes those alerts for an hour as the linked account, which needs
  `incidents.work`, with the reason "Muted from Discord". It is in the audit log, and the
  [Problems page](alerts.md) shows it with **+30 min** and **Unmute**. A webhook can't carry buttons.

- **Crew notices:** when a lead puts up a [crew notice](crew-notice.md), it is posted in the crew
  channel too: warning or info, who put it up and for how long. Taking it down posts nothing.

What people write in Discord threads is not copied back into Floorbit. That needs a gateway
connection and Discord's message content permission. Notes are added on the incident board.

## Slash commands

With the bot token and the app public key set, the bot also answers slash commands (epic #407).
Floorbit registers them with Discord by itself within a minute: on the crew's server when Discord
sign-in has a server ID (they show up at once), else in every server the bot is in. When you add the
bot to your server, give it the **applications.commands** scope as well as **bot**.

Answers are only shown to the person who asked, and they never ping anyone. A command counts as
the Floorbit account linked to that Discord user, with that account's permissions, the same as a
button click. There is no Discord role mapping.

| Command | What it answers |
| --- | --- |
| `/status` | how the network is doing: the state and since when, the affected areas, areas back up recently and the latest crew update. Crew with `incidents.work` also see the switch names. Anyone else sees only what the public [status page](status-page.md) shows, and only while that page is on. |
| `/seat <seat>` | one seat: online or not and how fast, its switch port, open incidents, needs-attention items and how often it was fixed before, with a link to it on the floor plan. Needs `incidents.work`. |
| `/switch <name>` | one switch: up or down and since when, its model, how many of its seats are online and which are not (with their ports). Needs `incidents.work`. |

| `/incident report <seat> <problem>` | files an incident for a seat, like the incident board does. It shows up there marked *From Discord*, and automatic dispatch applies. |
| `/incident take <incident>` | takes an open incident. Start typing a seat or a few words, and Discord lists the open incidents you may work. |
| `/incident fixed <incident> [note]` | marks it fixed, with an optional note on what you did. |
| `/jobs` | the incidents you have, oldest first. |

The incident commands follow the account's permissions exactly as on the board, and every change is
in the [audit log](audit.md).

`/seat` and `/switch` suggest seat numbers and switch names as you type, to crew only. They never
show nicks, IPs or MACs: those stay in Floorbit.

## Privacy

Messages show the seat, switch or circuit and what the crew wrote. They never show IPs, MACs or nicks.
An attendee's report from a seat QR code shows only its seat and the problem they picked. Messages
never mention anyone (`allowed_mentions` is empty).

## Setup

1. In the [Discord Developer Portal](https://discord.com/developers/applications), use the app you made
   for Discord sign-in ([auth.md](auth.md#sign-in-with-discord)), or make a new one. Under **Bot**,
   reset and copy the token.
2. Invite the bot to your server. It needs these permissions in the crew channel: View Channel, Send
   Messages, Create Public Threads, Send Messages in Threads, Manage Threads and Embed Links.
3. Under **Settings > Crew Discord channel**, enter the bot token and the channel ID. To copy the
   channel ID, right-click the channel and choose Copy Channel ID. Developer Mode must be on in
   Discord's settings.
4. For the buttons, copy the app's **Public Key** (General Information) into **App public key**.
   Then set **Interactions Endpoint URL** to `https://<your Floorbit>/api/discord/interactions`.
   Discord checks the URL when you save it, so Floorbit must be reachable from the internet. If
   Floorbit isn't reachable from the internet, leave the key empty: the messages and threads still
   work, just without the buttons.
5. Link the crew. Anyone who signs in with Discord once is linked. An admin can also enter a Discord
   user ID on the Users page.

| Setting | Default | |
|---|---|---|
| `DISCORD_BOT_TOKEN` | | the bot's token (a secret) |
| `DISCORD_CREW_CHANNEL` | | the crew channel's ID |
| `DISCORD_APP_PUBLIC_KEY` | | turns on the buttons |
| `DISCORD_CREW_ENABLED` | `true` | turn the channel off without removing the token |
| `DISCORD_CREW_INCIDENTS` | `true` | post incidents (off: only alerts, when there is no webhook) |
| `DISCORD_CREW_NOTICES` | `true` | post each [crew notice](crew-notice.md) a lead puts up |
| `DISCORD_CREW_WAITING_MINUTES` | `10` | say once in the thread when nobody has taken an incident for this long (`0`: never) |
| `DISCORD_CREW_UNSEEN_MINUTES` | `5` | say once in the thread when a sent job is not seen for this long (`0`: never) |
| `DISCORD_CREW_WAITING_ROLE` | | role ID to ping with that line |
| `DISCORD_CREW_FILE` | next to `data.json` | which message and thread belong to which incident |

`GET /api/integrations` shows the bridge's state under `crew`: whether it is configured, whether the
buttons are on, the last error and the interactions URL to paste into the portal.

## Security

`POST /api/discord/interactions` has no session. Discord calls it from its own servers. Floorbit
checks each request's Ed25519 signature against the app's public key and refuses requests signed
more than five minutes ago. When Discord sign-in has a server ID, clicks from other servers are
refused. Clicks from any channel other than the crew channel are refused too. Slash commands work in
any channel on that server. Every click that
changes an incident is written to the [audit log](audit.md) under the linked account.
