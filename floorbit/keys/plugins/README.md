# Plugin signing keys

The public keys (`*.pub`, PEM or base64 of the raw 32 bytes) of the Floorbit plugin key: plugins
signed with it are **official**. A Floorbit installs them from the Marketplace (docs/marketplace.md),
and an agent installs signed plugin updates only with one of these (docs/agent-plugins.md,
"Updates"). The agent image carries this folder; with no key in it, agents never install a bundle.

The private key lives only in the release workflow's `plugin-signing` environment
and each plugin repository's (`FLOORBIT_PLUGIN_SIGNING_KEY`), never on a hosted Floorbit. Make a pair with
`python scripts/agent_bundles.py keygen`.
