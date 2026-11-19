# Marketplace

Optional integrations (the LAN cache, Shelly, Home Assistant, UniFi, Aruba, MikroTik, Zabbix, Pi-hole, AdGuard Home) live in
repositories of their own and are installed from a signed Marketplace, the same way Hubra and
labdex do it. NetBox, LibreNMS, telemetry, the syslog and NetFlow relays and the health checks stay
built in.

Settings > Plugins shows the Marketplace below the installed plugins: install, update, go back to
the version an update replaced, or remove. An installed plugin starts **off**; turn it on in the list
above. Every install, update, rollback and removal is in the audit log.

## Where the plugins come from

| Repository | What it is |
| --- | --- |
| `bitsandbricks-ch/floorbit-plugins` | The official Marketplace: `plugins.yaml` lists the `floorbit-plugin-*` repositories, and its publish workflow builds a signed `index.json` from their releases (GitHub Pages). |
| `bitsandbricks-ch/floorbit-plugin-template` | What a new plugin repository starts from: the plugin, its tests, and the workflow that signs a release. |
| `bitsandbricks-ch/floorbit-plugin-<id>` | One plugin each. A `v<version>` tag builds the signed bundle and attaches it to the GitHub release. |

A release is one signed bundle (`<id>-<version>.tar.gz` with `SIGNATURE.json`), the same file the
[local agents](agent-plugins.md#updates) install, so a plugin's hosted part and its agent part
always come from the same signed release.

The index lists every version with its checksum, the Floorbit versions it works with
(`floorbit: ">=1.4"`) and, for a version that was pulled, why (`withdrawn:`). A withdrawn version is
never installed; where one runs, the page says so and offers the way out.

Each version in the index also says what it may touch, worked out from its `plugin.yaml` when the
index is built: the [areas](plugin-spec.md#data-floorbit-uses) it uses, the permissions its actions
and pages ask for, what its agent part sends and how private that is, the actions it can run in
the hall, and the device logins and secrets it uses. The Marketplace card shows that list before
you install. The build refuses a release whose `plugin.yaml` Floorbit would refuse.

## What is trusted

Only the official Marketplace, and only what is signed with the keys built into the image: the
plugin key in `floorbit/keys/plugins/` and the index key in `floorbit/keys/index/`. There are no
other sources or keys to add.

- Floorbit checks the index's signature, each download's checksum against the index, and the
  bundle's signature against those keys, at install and again every time it loads the plugin.
  A bundle that doesn't verify is refused, and a plugin whose files changed on disk doesn't load.
- Admins install, update, roll back and remove; they can't add a key or a source. So a stolen
  admin login can't make Floorbit, or an agent in the hall, run code nobody signed.
- The local agents trust the same plugin key, built into their own image, so every plugin
  installed here can run its agent part in the hall.

Floorbit used to take more sources and keys (`FLOORBIT_MARKETPLACE_SOURCES`,
`FLOORBIT_COMMUNITY_KEYS`). Both are ignored now. A plugin installed from such a source no longer
loads; Settings > Plugins says so, and an admin can remove it.

## Settings (environment only)

| Variable | Default | What |
| --- | --- | --- |
| `FLOORBIT_MARKETPLACE_URL` | `https://bitsandbricks-ch.github.io/floorbit-plugins/index.json` | The official index. Its signature must verify with `floorbit/keys/index/`, wherever it is served from. |
| `FLOORBIT_PLUGIN_DIR` | `plugins/` next to the data | Where installed plugins are unpacked, as `<id>/<version>/`, with their bundles in `.archives/`. |

Which version of each plugin runs is kept in `marketplace.json` with the rest of the data (or in
the database). With several instances, each one checks it every minute and downloads what it lacks,
so a pod that starts on an empty disk ends up with the same plugins. When a download fails (the
index or GitHub is away), it tries again after a minute, then less often, up to every half hour,
until it has them. The index and bundles are read with a size cap, so they can't fill the
server's memory.

While the index is away, its last good copy is used for up to a day, and the page says which copy
it shows. An index older than one this server already read is refused even when its signature is
fine: someone serving an old copy can't hide that a version was withdrawn since.

## Updates and rollback

An update keeps the version it replaced. If the new one doesn't load (a broken `plugin.py`, a
manifest error), the old one keeps running and the page says why. *Back to* swaps the two, so a
rollback can be undone the same way. Settings and state stay when a plugin is updated, rolled back
or removed.

The agents follow on their own: a plugin installed here is offered to every agent that
runs it, and the agent's own update policy (`FLOORBIT_AGENT_PLUGIN_UPDATES`) decides when it
installs it ([Updates](agent-plugins.md#updates)).

## Tools

`scripts/marketplace.py` is what the plugin repositories and floorbit-plugins run:

```
python scripts/marketplace.py sign <plugin folder> --key plugin-key.pem --version 1.2.0 --out dist
python scripts/marketplace.py build-index plugins.yaml site --key index-key.pem
python scripts/marketplace.py check https://bitsandbricks-ch.github.io/floorbit-plugins/index.json
```

Each refuses a key that isn't the one built into Floorbit for its purpose, and a key pinned for
both. Make a key pair with `openssl genpkey -algorithm ed25519 -out key.pem` and
`openssl pkey -in key.pem -pubout -out key.pub`.
