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

What people write in Discord threads is not copied back into Floorbit. That needs a gateway
connection and Discord's message content permission. Notes are added on the incident board.

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
| `DISCORD_CREW_FILE` | next to `data.json` | which message and thread belong to which incident |

`GET /api/integrations` shows the bridge's state under `crew`: whether it is configured, whether the
buttons are on, the last error and the interactions URL to paste into the portal.

## Security

`POST /api/discord/interactions` has no session. Discord calls it from its own servers. Floorbit
checks each request's Ed25519 signature against the app's public key and refuses requests signed
more than five minutes ago. When Discord sign-in has a server ID, clicks from other servers are
refused. Clicks from any channel other than the crew channel are refused too. Every click that
changes an incident is written to the [audit log](audit.md) under the linked account.
