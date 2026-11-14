import type { SeatRow } from '@/api/types'

export function matches(row: SeatRow, query: string, onlyManual: boolean) {
  if (onlyManual && !row.manual) return false
  const q = query.trim().toLowerCase()
  if (!q) return true
  return [row.seat, row.nick, row.ip, row.mac, row.manual?.note ?? ''].some((v) => v.toLowerCase().includes(q))
}

/** Reads a picked file as text in the browser; the server checks every row. */
export function readText(file: File): Promise<string> {
  if (typeof file.text === 'function') return file.text()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(file)
  })
}
