export const BYTES = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
export const BITS = ['bit/s', 'kbit/s', 'Mbit/s', 'Gbit/s', 'Tbit/s']

/** 24.7 TB as the number and its unit (floorbit/stats_wall.py writes the same for /wall.json users). */
export function scaled(value: number, units: string[], lang: string): [string, string] {
  let n = value || 0
  let i = 0
  while (n >= 1000 && i < units.length - 1) { n /= 1000; i++ }
  const digits = n >= 100 || i === 0 ? 0 : 1
  return [n.toLocaleString(lang, { minimumFractionDigits: digits, maximumFractionDigits: digits }), units[i]]
}
