# Applications

The games, launchers and site groups Floorbit recognises in [DNS](dns.md), [traffic](flows.md) and
the [LAN cache](lancache.md). They feed [Games](games.md), the stats wall and the traffic pages. The
page is **Traffic › Applications** (`/applications`), and `GET /api/applications` answers the same.

Every application is one of three kinds:

| Kind | What it is | Example |
| --- | --- | --- |
| **Game** | One title. It can be part of a launcher. | Valorant, part of Riot Games |
| **Launcher** | A store or launcher and its download CDN. | Steam, Battle.net, Epic Games |
| **Site group** | Sites that belong together. | Streaming, Voice and chat, Windows updates |

Each one is recognised by any of:

- **Domains**, counted per site (`cdn.example.com` counts as `example.com`), from the resolver's
  lookups under the five-seat rule.
- **Ports** (`udp/27015`, `tcp/6881-6889`) and **server addresses** (`198.51.100.0/28`), from the
  flows. The agent's flow collector gets these with the seat addresses, within a minute of a change.
- **LAN cache**: the lancache.net cache it owns (`steam`, `blizzard`, ...) and, for Steam, depot ids
  (the number in `/depot/<id>/`).
- **Game servers** (Settings › Game servers) count for the game they run: by its name or id, its
  players as players, and its address as a traffic rule. A server set up by host name has no traffic
  rule: the agent can't match flows to a name.

## Built in

Floorbit ships two open lists, at a fixed commit, so nothing is fetched during an event (their licences: `floorbit/applications_lists.LICENSES.md`):

- [uklans/cache-domains](https://github.com/uklans/cache-domains) (MIT): the CDNs lancache-dns
  answers for. Its entries become launchers, games (Call of Duty, Guild Wars 2, Warframe, ...) and
  the "Windows updates" site group, so Games splits the hall the same way the cache does.
- [v2fly/domain-list-community](https://github.com/v2fly/domain-list-community) (MIT): the site
  groups Streaming, Music, Voice and chat, Social media and FACEIT.

A site in more than one list, and shared CDNs (`edgesuite.net`, `akamaihd.net`, ...), count for
nobody: DNS only sees the site, so it can't tell whose download it was. On top come the ports the
launchers publish and a few game titles no open list has (`STARTER` in `floorbit/applications.py`).
TODO: ask Mike which games the event plays most, and check their domains and ports before an event.

`python scripts/applications_import.py` writes `floorbit/applications_lists.json` from the commits
named in the script. Change them there to move to newer lists, and check the diff.

## The event's own

With `settings.manage` you can:

- **add** a game, launcher or site group of your own (tournament servers, a mod's master server);
- **add** domains, ports, addresses and depots **to a built-in one** (it keeps its own);
- **hide** a built-in one, and **reset** it to how it shipped.

Changes are kept in the event (`applications` in data.json) and written to the audit log.

## Privacy

Nothing here is per seat. An application's numbers are what DNS and traffic already show hall-wide:
a domain counts once 5 or more seats looked it up in an hour, a flow service once 5 or more seats
used it. Players on the event's own game servers are the server's count.

## API

- `GET /api/applications?hours=24` (1 to 168): every application with `kind`, `part_of`, its matches,
  `builtin`, `edited`, `hidden`, what the event `added`, and `seen` (lookups, most seats in an hour
  by DNS, traffic bytes and seats, LAN cache bytes, players, and `seats`, the most of those).
- `POST /api/applications`, `PUT /api/applications/<id>`: `{name, kind, category, part_of, sites,
  ports, cidr, depots, hidden}`; a built-in one takes only the lists and `hidden`.
- `DELETE /api/applications/<id>`: removes an own one, or resets a built-in one.
