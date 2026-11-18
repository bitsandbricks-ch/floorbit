// Speedtest at the seat (issue #99): latency, download and upload to the Floorbit server, run from
// the seat's help page. The browser measures; the server only sends and swallows bytes. Only the
// numbers are sent back. See docs/speedtest.md and floorbit/blueprints/speedtest.py.

const MB = 1024 * 1024
const MAX_UP = 24 * MB
const MAX_DOWN = 200 * MB
const PHASE_MS = 6000        // time spent on download, then on upload
// Or until half of what one test may move (Settings > Speed tests), a little under so the server's
// per-seat limit never cuts the last request off.
const phaseBytes = (testMb: number) => Math.floor(testMb * MB / 2 * 0.95)
const AIM_MS = 1500          // each request should take about this long

export type Figure = 'down' | 'up' | 'ping'
export interface SpeedResult { down_mbps: number | null; up_mbps: number | null; ping_ms: number; jitter_ms: number }

const now = () => performance.now()
const mbps = (bytes: number, ms: number) => bytes * 8 / (ms / 1000) / 1e6

async function check(resp: Response) {
  if (resp.ok) return resp
  const body = await resp.json().catch(() => ({})) as { error?: string }
  throw new Error(body.error || `HTTP ${resp.status}`)
}

function randomBlob(size: number) {
  const block = new Uint8Array(MB)
  for (let i = 0; i < MB; i += 65536) crypto.getRandomValues(block.subarray(i, i + 65536))
  const parts: Uint8Array[] = []
  for (let n = 0; n < size; n += MB) parts.push(n + MB <= size ? block : block.subarray(0, size - n))
  return new Blob(parts as BlobPart[])
}

/** Runs the test for ``seat`` with the signed link's ``k`` and saves the result for the seat,
 *  moving at most ``testMb`` MB. ``show`` gets each figure as it comes in, in Mbit/s or ms. */
export async function runSpeedtest(seat: string, k: string, show: (what: Figure, value: number) => void,
  testMb = 250): Promise<SpeedResult> {
  const most = phaseBytes(testMb)
  const base = `/help/${encodeURIComponent(seat)}/speed/`
  const url = (what: string, extra = '') => `${base}${what}?k=${encodeURIComponent(k)}${extra}`

  const times: number[] = []
  for (let i = 0; i < 11; i++) {
    const t0 = now()
    await check(await fetch(url('ping', `&n=${i}`), { cache: 'no-store' }))
    if (i > 0) times.push(now() - t0)   // the first one sets up the connection
  }
  const sorted = [...times].sort((a, b) => a - b)
  const ping = sorted[Math.floor(sorted.length / 2)]
  let jitter = 0
  for (let j = 1; j < times.length; j++) jitter += Math.abs(times[j] - times[j - 1])
  jitter /= times.length - 1
  show('ping', ping)

  async function downOnce(size: number) {
    const t0 = now()
    const resp = await check(await fetch(url('down', `&bytes=${size}`), { cache: 'no-store' }))
    const reader = resp.body!.getReader()
    let got = 0
    for (;;) {
      const part = await reader.read()
      if (part.done) break
      got += part.value.length
    }
    return { bytes: got, ms: now() - t0 }
  }

  async function upOnce(size: number) {
    const blob = randomBlob(size)
    const t0 = now()
    await check(await fetch(url('up'), { method: 'POST', body: blob, cache: 'no-store',
      headers: { 'Content-Type': 'application/octet-stream' } }))
    return { bytes: size, ms: now() - t0 }
  }

  // Requests sized to take about AIM_MS each, for PHASE_MS; the first one only finds the size.
  async function phase(once: (size: number) => Promise<{ bytes: number; ms: number }>, cap: number, what: Figure) {
    let size = MB, bytes = 0, ms = 0, moved = 0, first = true
    const start = now()
    while (now() - start < PHASE_MS && most - moved >= MB) {
      const r = await once(size)
      moved += r.bytes
      if (!first) { bytes += r.bytes; ms += r.ms; show(what, mbps(bytes, ms)) }
      first = false
      const rate = r.bytes / Math.max(r.ms, 1)
      size = Math.max(MB, Math.min(cap, most - moved, Math.round(rate * AIM_MS / MB) * MB))
    }
    return ms ? mbps(bytes, ms) : null
  }

  const down = await phase(downOnce, MAX_DOWN, 'down')
  const up = await phase(upOnce, MAX_UP, 'up')
  const result: SpeedResult = { down_mbps: down, up_mbps: up, ping_ms: ping, jitter_ms: jitter }
  await check(await fetch(url('result'), { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(result) }))
  return result
}
