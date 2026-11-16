### Added

- Switch logins kept by Floorbit (Settings > Switch logins): one for every switch, a name pattern or one switch, encrypted with AES-256-GCM under a key outside the data (`FLOORBIT_SECRET_KEY_FILE`), write-only, opened only for the one SSH connection and audit-logged on every use. Port actions, switch commands and the terminal use them instead of asking each tech; a typed login still wins. `python -m floorbit.vault rotate` moves them to a new key.
