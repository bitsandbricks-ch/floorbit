### Security

- Failed sign-ins no longer pile up in memory: every made-up username counted as a new entry and
  was never forgotten. Stale entries are now dropped, and only the first 200 characters of a name count.
