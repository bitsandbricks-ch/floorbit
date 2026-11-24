// Dashboard tiles asked for in the same moment go to the server as one request (issue #1300):
// 30 tiles as 30 requests queued for the one server process, each a few seconds.
import { ApiError, get } from './client'

const BATCHED = /^\/api\/(dashboard\/floorbit\/[\w-]+|plugins\/[\w.-]+\/widgets\/[\w.-]+)(\?|$)/
/** Tiles per request: keeps the address well under what proxies take (8 KB). */
const PER_REQUEST = 20
/** How long to wait for the other tiles of the same render before asking. */
const GATHER_MS = 10

interface Waiting { url: string; resolve: (value: unknown) => void; reject: (error: unknown) => void }
interface Result { status: number; body: Record<string, unknown> }

let waiting: Waiting[] = []
let timer: ReturnType<typeof setTimeout> | null = null

async function send(batch: Waiting[]) {
  if (batch.length === 1) {
    get(batch[0].url).then(batch[0].resolve, batch[0].reject)
    return
  }
  const query = batch.map((w) => `u=${encodeURIComponent(w.url)}`).join('&')
  let results: Result[]
  try {
    results = (await get<{ results: Result[] }>(`/api/dashboard/widgets?${query}`)).results
  } catch (err) {
    batch.forEach((w) => w.reject(err))
    return
  }
  batch.forEach((w, i) => {
    const r = results[i]
    if (!r) w.reject(new ApiError('HTTP 500', 500))
    else if (r.status >= 400) w.reject(new ApiError(typeof r.body.error === 'string' ? r.body.error : `HTTP ${r.status}`, r.status, r.body))
    else w.resolve(r.body)
  })
}

function flush() {
  timer = null
  const all = waiting
  waiting = []
  for (let i = 0; i < all.length; i += PER_REQUEST) void send(all.slice(i, i + PER_REQUEST))
}

/** ``get(url)`` for a tile, sent together with the other tiles asked for in the next few ms. */
export function getWidget<T>(url: string): Promise<T> {
  if (!BATCHED.test(url)) return get<T>(url)
  return new Promise<T>((resolve, reject) => {
    waiting.push({ url, resolve: resolve as (value: unknown) => void, reject })
    timer ??= setTimeout(flush, GATHER_MS)
  })
}
