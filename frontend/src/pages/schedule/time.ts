const pad = (n: number) => String(n).padStart(2, '0')

/** Epoch seconds as the value of an <input type="datetime-local">, in the browser's time zone. */
export function toInput(ts: number): string {
  const d = new Date(ts * 1000)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** A datetime-local value back to epoch seconds (the browser reads it as local time). */
export function fromInput(value: string): number {
  return Math.round(new Date(value).getTime() / 1000)
}
