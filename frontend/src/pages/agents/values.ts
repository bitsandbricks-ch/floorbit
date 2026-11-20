/** A value Floorbit sets on an agent; ``null`` resets it. */
export type Value = string | number | string[] | boolean | null

export function shown(v: unknown): string {
  if (Array.isArray(v)) return v.join(', ')
  if (v === null || v === undefined || v === '') return ''
  return String(v)
}

export const fieldId = (key: string) => `agent-setting-${key.replace(/[^a-z0-9]+/gi, '-')}`
