### Fixed

- After the database connection pool is closed, a connection another thread still held is closed
  when it comes back instead of going back into the pool.
