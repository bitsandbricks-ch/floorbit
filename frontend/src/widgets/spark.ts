export function sparkPoints(points: number[], min?: number, max?: number): string {
  if (points.length < 2) return ''
  const lo = min ?? Math.min(...points)
  const hi = max ?? Math.max(...points)
  const span = hi - lo || 1
  return points.map((p, i) => `${(i / (points.length - 1)) * 100},${30 - ((p - lo) / span) * 28 - 1}`).join(' ')
}
