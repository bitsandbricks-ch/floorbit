/** One step of a seat walk Locate, as the server sends it live (`seat-walk.trace`) and in the answer
 *  (floorbit/seat_walk.py `Trace`, issue #1359). The page words it from `code`. */
export type TraceState = 'ok' | 'no' | 'skip' | 'warn' | 'run'
export interface TraceStep {
  /** ms since the epoch, from the server's clock. */
  at: number
  code: string
  state: TraceState
  /** How long this step took, when it was one call. */
  ms?: number
  /** ip and mac are left out for pages that may not see the laptop. */
  args: Record<string, string | number | string[] | null | undefined>
}
/** What the live bus carries for one step. */
export interface TraceEvent { run: string; seat: string | null; step: TraceStep }

/** A random id for one Locate, so the page only listens to its own steps. */
export function newRun(): string {
  const c = globalThis.crypto as Crypto | undefined
  if (c?.randomUUID) return c.randomUUID()
  return `run-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

/** Steps from the live bus and from the answer, each once, in time order. */
export function mergeSteps(have: TraceStep[], more: TraceStep[], max = 300): TraceStep[] {
  const key = (s: TraceStep) => `${s.at}|${s.code}|${String(s.args.switch ?? '')}|${String(s.args.port ?? '')}`
  const seen = new Set(have.map(key))
  const out = [...have]
  for (const s of more) {
    if (seen.has(key(s))) continue
    seen.add(key(s))
    out.push(s)
  }
  out.sort((a, b) => a.at - b.at)
  return out.length > max ? out.slice(out.length - max) : out
}
