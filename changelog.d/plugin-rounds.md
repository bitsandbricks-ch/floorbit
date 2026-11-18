### Fixed

- The LAN cache, Shelly and Home Assistant plugins keep reading for the whole event when a round goes wrong: one odd answer (something that isn't a web server at the cache or meter address, a meter that answers NaN or a list, Home Assistant answering something other than its list of states) used to stop the plugin's reading thread until the agent restarted. Now it is a warning or a failed meter, and the next round runs as usual.
- The LAN cache plugin reads on past a log full of zeros (as after a crash) and past an edited positions file, instead of stopping at the same place every round. Its DNS check gives up after its timeout even when other answers keep arriving.
