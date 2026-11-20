import { useSearchParams } from 'react-router-dom'

/** A list's search and filters, kept in the address (?q=…&state=…) so a link or a reload shows the
 *  same view (#1020). A value equal to its default is left out of the address. */
export function useFilters<K extends string>(defaults: Record<K, string>) {
  const [params, setParams] = useSearchParams()
  const keys = Object.keys(defaults) as K[]
  const values = Object.fromEntries(keys.map((k) => [k, params.get(k) ?? defaults[k]])) as Record<K, string>
  const search = params.get('q') ?? ''
  const write = (change: (p: URLSearchParams) => void) =>
    setParams((p) => { const next = new URLSearchParams(p); change(next); return next }, { replace: true })
  const set = (key: K, value: string) => write((p) => { if (value === defaults[key]) p.delete(key); else p.set(key, value) })
  const setSearch = (value: string) => write((p) => { if (value) p.set('q', value); else p.delete('q') })
  const changed = !!search || keys.some((k) => values[k] !== defaults[k])
  const clear = () => write((p) => { p.delete('q'); keys.forEach((k) => p.delete(k)) })
  return { values, set, search, setSearch, changed, clear, defaults }
}
