### Changed

- The sign-in page is part of the React app and speaks German too, with a language picker. When a
  Discord or OpenID Connect sign-in fails, the page says why, as before. A plain form post to
  `/login` still works for scripts.

### Security

- `next` after signing in now also refuses `/\example.com`, which browsers read as another site.
