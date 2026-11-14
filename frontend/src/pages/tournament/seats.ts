/** B-1, B-2, B-3, B-7 as "B-1..B-3, B-7": the same way the zone is typed. */
export function compact(seats: string[]): string[] {
  const out: string[] = []
  let run: [string, number, number] | null = null
  const flush = () => {
    if (run) out.push(run[1] === run[2] ? `${run[0]}-${run[1]}` : `${run[0]}-${run[1]}..${run[0]}-${run[2]}`)
  }
  for (const seat of seats) {
    const m = /^(.*)-(\d+)$/.exec(seat)
    if (!m) { flush(); run = null; out.push(seat); continue }
    const n = Number(m[2])
    if (run && run[0] === m[1] && n === run[2] + 1) { run[2] = n; continue }
    flush()
    run = [m[1], n, n]
  }
  flush()
  return out
}
