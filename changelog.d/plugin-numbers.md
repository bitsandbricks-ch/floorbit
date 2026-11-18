### Fixed

- A plugin whose `plugin.yaml` has a value of the wrong type (a refresh that isn't a whole number of seconds, an id or label that isn't text, a list where a single entry belongs) now shows that as its own error, instead of stopping Floorbit from loading its plugins. Odd numbers in a Marketplace index no longer break the Marketplace.
- A plugin tile, layer or data endpoint that answers with something of the wrong shape (a list that isn't a list, a number that is NaN or infinite) now gives the plugin's error and a line in its log, instead of a server error or an answer the browser can't read. An action with a body that isn't a JSON object, or an infinite whole number, is refused before the plugin runs.
- A Marketplace bundle whose plugin.yaml names another installed plugin is refused before it loads; it used to replace that plugin until the next restart.
- Translating a plugin's text (or an error message) with several `{}` in it could take seconds on a long text that didn't match; it now takes the same short time whatever the text.
- Any request whose JSON holds `NaN`, `Infinity` or a number too large for a float (`1e999`) is refused with a clear message. Before, five editor routes and every whole-number setting answered with a server error.
- A NaN or infinite number from a monitoring source (Prometheus answers `NaN` for a rate over nothing) no longer makes the whole answer unreadable for the browser: it is sent as empty.
- A plugin just turned on no longer reads as off for up to two seconds when another request read the plugin list at the same moment.
- Two Floorbit pods sharing one plugin folder can fetch the same Marketplace version at once without one deleting the other's half-unpacked copy.
- A Marketplace source that sends its index or a bundle a byte at a time is given up on after a minute (an index) or four (a bundle) instead of holding a server worker for hours.
