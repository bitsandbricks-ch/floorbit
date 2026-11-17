### Fixed

- About 40 write API endpoints answered "500 Internal Server Error" when a script sent a JSON body that wasn't an object (a string, number or list). They now answer 400 "Send a JSON object." (German too). A garbled body to the cache endpoint no longer clears the whole cache.
