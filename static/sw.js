// Floorbit's service worker: what makes the app installable on a phone (Mike, 2026-11-26) and
// opens it quickly. It keeps the built app's files, never data: /api answers, sign-in and live
// updates always go to the server, so nothing shown is stale or left on a lost phone.
const CACHE = 'floorbit-app-v1'
const KEEP = 600   // files: a release has about 300

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== CACHE) await caches.delete(key)
    await self.clients.claim()
  })())
})

const OFFLINE = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Floorbit</title><body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0b0f;color:#e8e8ee;font:16px system-ui,sans-serif;text-align:center">
<div><p style="font-size:20px;font-weight:600;margin:0 0 8px">No connection to Floorbit</p>
<p style="margin:0 0 16px;opacity:.7">Floorbit shows the network live, so it needs the server.</p>
<button onclick="location.reload()" style="font:inherit;padding:8px 16px;border-radius:8px;border:1px solid #333;background:#16161d;color:inherit">Try again</button></div></body></html>`

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.origin !== self.location.origin) return
  // Pages: always the server's, with a short note when it can't be reached.
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(() => new Response(OFFLINE, { headers: { 'Content-Type': 'text/html; charset=utf-8' } })))
    return
  }
  // The build's files carry a hash in their name, so a kept copy is never out of date.
  if (url.pathname.startsWith('/static/app/assets/') || url.pathname.startsWith('/static/fonts/')) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE)
      const hit = await cache.match(req)
      if (hit) return hit
      const res = await fetch(req)
      if (res.ok) {
        await cache.put(req, res.clone())
        // Each release brings new file names: drop the oldest so the phone doesn't fill up.
        const keys = await cache.keys()
        for (const old of keys.slice(0, Math.max(0, keys.length - KEEP))) await cache.delete(old)
      }
      return res
    })())
  }
  // Everything else (data, live updates, other static files) goes to the server as usual.
})
