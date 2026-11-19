import { useSearchParams } from 'react-router-dom'

/** The tab in ``?tab=``, or the first: tabs stay in the address, so a link or a reload opens the
 *  same tab and the browser's back button goes to the one before. */
export function usePageTab(ids: string[], param = 'tab'): [string, (id: string) => void] {
  const [params, setParams] = useSearchParams()
  const asked = params.get(param)
  const current = asked && ids.includes(asked) ? asked : ids[0] ?? ''
  const set = (id: string) => setParams((p) => {
    const next = new URLSearchParams(p)
    if (id === ids[0]) next.delete(param)
    else next.set(param, id)
    return next
  })
  return [current, set]
}
