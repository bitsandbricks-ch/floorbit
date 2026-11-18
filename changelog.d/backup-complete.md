### Fixed

- A backup now holds the cabling and power too: cables and their drawn routes, patch panels, uplinks between switches, port areas, and the power boards and circuits. Before, restoring a backup brought back the switches and seat blocks but kept whatever cables and power were there, so a restored plan could show cables to switches that weren't on it any more. A restore replaces these parts as a whole and checks them with the editor's rules first; a backup from an older version, which has none of them, leaves them as they are and says so (#810).
