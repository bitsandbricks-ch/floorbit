# Agent plugin signing keys

The public keys (`*.pub`, PEM or base64 of the raw 32 bytes) an agent trusts for signed plugin
bundles (docs/agent-plugins.md, "Updates"). The agent image carries this folder; with no key in it,
agents never install a bundle and run the plugins their image came with.

The private key lives only in the release workflow's `plugin-signing` environment
(`FLOORBIT_PLUGIN_SIGNING_KEY`), never on a hosted Floorbit. Make a pair with
`python scripts/agent_bundles.py keygen`.
