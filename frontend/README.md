# Floorbit frontend

The React app: React 19, TypeScript, [Mantine](https://mantine.dev), TanStack Query and
react-router, built with Vite. It is set up like Hubra's `app/frontend` (by Mike), and some
pieces come from there (marked in the files). Flask stays the API and serves the pages; see
[docs/architecture.md](../docs/architecture.md#react-app-frontend).

## Develop

```sh
cd frontend
npm ci              # Node 24 / npm 11 (the lock file needs npm 11)
npm run dev          # http://localhost:5173, API and sign-in proxied to Flask on :5000
```

Start Flask as usual (`python app.py`) next to it. Set `FLOORBIT_URL` if Flask runs elsewhere.
Sign in on `http://localhost:5173/login`: the proxy passes the session cookie through.

## Check, like CI

```sh
npm run lint
npm run typecheck
npm test
npm run build        # writes ../static/app/, which Flask serves
```

## Rules

- A page is a file in `src/pages/` and a route in `src/App.tsx`. Point its Flask route at
  `spa.render('<Title>')` (`floorbit/spa.py`), so Flask still checks sign-in and roles.
- Every text goes through `t()` with a key in `src/i18n/en/<feature>.json` **and**
  `src/i18n/de-CH/<feature>.json` (Swiss spelling, no "ß"). The i18n test fails otherwise.
- Colours come from the design tokens (`var(--color-...)`), never hex values, so themes work.
- Text from the API or a plugin is shown as text. No `dangerouslySetInnerHTML` (ESLint refuses it).
- Query keys come from `src/api/keys.ts`.
- Added a translation file and the tests don't see it? Vitest caches transforms: delete
  `node_modules/.vitest-cache`.
