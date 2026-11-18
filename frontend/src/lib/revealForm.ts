import { useCallback, useEffect, useRef } from 'react'

/** A form or panel that opens inline, maybe below the fold on a phone: scroll it into view and put
 *  the cursor in its first field, so a tap on "Add" or a list row visibly does something. */
export function revealForm(el: HTMLElement | null) {
  if (!el) return
  const reduced = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  el.scrollIntoView?.({ block: 'nearest', behavior: reduced ? 'auto' : 'smooth' })
  el.querySelector<HTMLElement>('input:not([type=hidden]):not([disabled]), textarea:not([disabled])')?.focus({ preventScroll: true })
}

/** ``revealForm`` for a panel that stays mounted and changes what it shows: call ``ask()`` from the
 *  click that changes it, and the panel is revealed once the change has rendered. A page that opens
 *  with something shown (a link to it) is not scrolled. */
export function useReveal(shown: unknown): [(el: HTMLElement | null) => void, () => void] {
  const el = useRef<HTMLElement | null>(null)
  const want = useRef(false)
  useEffect(() => {
    if (!want.current) return
    want.current = false
    revealForm(el.current)
  }, [shown])
  const attach = useCallback((node: HTMLElement | null) => { el.current = node }, [])
  const ask = useCallback(() => { want.current = true }, [])
  return [attach, ask]
}
