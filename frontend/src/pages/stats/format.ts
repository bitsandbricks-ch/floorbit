/** Bits per second, the way network people read them: 940 Mbps, 2.4 Gbps. */
export function bps(value: number | null | undefined): string {
  const v = value ?? 0
  if (v >= 1e9) return `${(v / 1e9).toFixed(v >= 1e10 ? 0 : 1)} Gbps`
  if (v >= 1e6) return `${(v / 1e6).toFixed(v >= 1e8 ? 0 : 1)} Mbps`
  if (v >= 1e3) return `${Math.round(v / 1e3)} kbps`
  return `${Math.round(v)} bps`
}
