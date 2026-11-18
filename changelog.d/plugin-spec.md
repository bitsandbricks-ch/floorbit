### Added

- [What a plugin can ship](docs/plugin-spec.md): one page with everything a plugin may bring
  (settings, actions, tiles, data sources, the part on the local agent, storage, German), where
  each part runs, the limits, and what is planned next.

### Security

- A plugin whose `plugin.yaml` has a key Floorbit doesn't know is refused when it loads, and a
  plugin bundle with browser code (JavaScript, CSS, HTML) or native code is never signed or
  installed.
