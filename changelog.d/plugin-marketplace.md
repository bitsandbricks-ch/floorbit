### Added

- A plugin Marketplace under Settings > Plugins: install, update, roll back and remove signed
  plugins from the official index, and from sources the server's operator adds. Floorbit checks
  every index and download against keys built into the image (or trusted by the operator), never
  installs a withdrawn version, and keeps the old version running when a new one fails to load.
  Official plugins installed here reach the local agents too. Every change is in the audit log.
  See docs/marketplace.md.
