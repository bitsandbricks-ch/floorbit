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

Floorbit ships two open lists at a fixed commit. They are the fallback that works with no internet;
lists that should stay current are [rule sources](#rule-sources). Their licences are in
`floorbit/applications_lists.LICENSES.md`:

- [uklans/cache-domains](https://github.com/uklans/cache-domains) (MIT): the CDNs lancache-dns
  answers for. Its entries become launchers, games (Call of Duty, Guild Wars 2, Warframe, ...) and
  the "Windows updates" site group, so Games splits the hall the same way the cache does.
- [v2fly/domain-list-community](https://github.com/v2fly/domain-list-community) (MIT): the site
  groups Streaming, Music, Voice and chat, Social media and FACEIT. Its publisher lists add each
  launcher's own sites (log-in, store, matchmaking), which the cache CDNs alone miss: Steam,
  Battle.net, EA app, Epic Games, Riot Games, Ubisoft Connect, Xbox, PlayStation Network,
  Nintendo, Rockstar, Wargaming, Escape from Tarkov and Nexus Mods. From its games category come
  publishers, stores and mod sites cache-domains doesn't have: GOG, itch.io, Roblox, PUBG, osu!,
  VRChat, HoYoverse, Supercell, Gaijin, Embark Studios, Bohemia Interactive, CD PROJEKT, Nexon,
  Garena, Konami, WB Games, CurseForge and Modrinth. A publisher of several games is a site group.

A site in more than one list, shared CDNs (`edgesuite.net`, `akamaihd.net`, ...) and services
many games use (anti-cheat, captcha, support desks), count for nobody: DNS only sees the site, so it can't tell whose download it was. On top come the ports the
launchers publish and a few game titles no open list has (`STARTER` in `floorbit/applications.py`).
TODO: ask Mike which games the event plays most, and check their domains and ports before an event.

`python scripts/applications_import.py` writes `floorbit/applications_lists.json` from the commits
named in the script. Change them there to move to newer lists, and check the diff.

## Sharing

An application's panel has **Share** (`settings.manage`). It shows what would leave this Floorbit:
the id, name, kind, category, what it is part of, and its domains, ports, addresses and depots. No
seats, numbers or anything about the event go with it. It also shows how many seats it was seen by
here in the last 24 hours, so a wrong entry shows up before it is shared. It asks where its facts
come from (a link or a note), then:

- **Open on GitHub** opens bitsandbricks-ch/floorbit-plugins with `games/<id>.yaml` filled in. Your
  own GitHub account opens the pull request; its check shows what the entry adds. Once it is merged,
  every Floorbit gets it with Floorbit's own list. An entry too big for GitHub to fill in is
  downloaded and added by hand.
- **Download as rules file** gives the entry to another event directly.

**Not recognised**, above the list, shows the busiest domains 5 or more seats used that no shown
application has, each with **Make an application** (the domain filled in). That is where a new game
usually shows up first.

When Floorbit's lists come to have everything the event added to a built-in application (because it
was shared, or a list caught up), its panel offers **Drop the local copy**.

**Export** on the page downloads the event's own applications and what it added to built-in ones as
one rules file. **Import** on another Floorbit takes such a file. New applications keep their ids,
own ones are replaced, and a built-in one gets only what the file has beyond what it shipped with.
The same file also works as a [rule source](#rule-sources).

## Rule sources

**Rule sources** (button on the page, `settings.manage`) are rules files Floorbit fetches on a
schedule, on top of the built-in lists. Each has a name, an https URL, how often to fetch it (every
24 hours unless set) and an on/off switch.

A file is one of:

- **A rules file**, the page's own shape:

  ```json
  {"version": 1, "applications": [
    {"id": "example-arena", "name": "Example Arena", "kind": "game", "category": "gaming",
     "part_of": "steam", "sites": ["arena.example.com"], "ports": ["udp/7777"],
     "cidr": ["198.51.100.0/28"], "depots": []}
  ]}
  ```

  Every entry is checked as the page checks one. One bad entry keeps the whole file out.
- **A plain domain list**, in uklans/cache-domains style (one domain per line, `*.` allowed) or
  v2fly style (`domain:`, `full:`; `include:` and `regexp:` lines are left out). It becomes one
  site group named after the source.

**Floorbit's own list** is always there, last in the list and on by default. It is `applications.json`
next to the Marketplace's index (`https://bitsandbricks-ch.github.io/floorbit-plugins/applications.json`),
built by floorbit-plugins' publish workflow from its curated `games/` folder (`scripts/marketplace.py
build-applications`) and signed with the Marketplace's index key. Floorbit uses a copy only when the
signature checks out against `floorbit/keys/index/`; an unsigned or changed file keeps the last good
copy. It can be switched off (and fetched less often), not removed or moved: your own sources win over
it. To add a game for every Floorbit, open a pull request adding `games/<id>.yaml` in bitsandbricks-ch/floorbit-plugins,
with a `source:` that says where its domains and ports come from.

How it behaves:

- **Fetching:** the hosted Floorbit fetches through the outbound guard (`OUTBOUND_BLOCK_NETS`, see
  [integrations](integrations.md)). It refuses files over 4 MB and gives up on a source that stops answering.
- **Last good copy:** a source keeps its last good copy. A fetch that fails, or a file that doesn't
  pass the checks, leaves that copy in use, and the page shows why. A failed fetch is tried again
  after 15 minutes. Copies are kept in the event (`application-sources.json`).
- **Order:** when two name the same application (by `id`), the winner is chosen in this order:
  1. the event's own changes;
  2. the sources, from the top of the list down ("Move to top");
  3. Floorbit's own list;
  4. the built-in lists.

  A source's entry replaces the built-in one but keeps its LAN cache ids.
- **Freeze:** stops all fetching during the event, so the numbers don't move. The copies stay in
  use. The page footer shows the frozen state and when each source last changed.
- **Last change:** each source shows what its last sync changed: how many applications came,
  changed or went, and their names.

The agent's traffic rules come from the merged list, so a synced port or address reaches the flow
collector within a minute, as an edit on the page does.

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
- `POST /api/applications/import` `{file}`: takes a rules file (another Floorbit's Export) into the
  event's own applications; answers `{added, changed}`.
- `GET /api/applications` also has `synced` (each source's name, whether it is on, `ok`, `changed_at`
  and `count`; no URL) and `frozen`.
- Rule sources (`settings.manage`, reading too, since a URL can carry a token):
  `GET|POST /api/applications/sources`, `PUT|DELETE /api/applications/sources/<id>` (`{name, url,
  every_hours, on, position}`), `POST /api/applications/sources/<id>/sync` (409 while frozen), and
  `PUT /api/applications/sources-frozen` (`{frozen}`).
