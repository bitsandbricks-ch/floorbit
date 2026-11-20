import { useEffect, useState } from 'react'

/** The height from ``el``'s top down to the status line under the page: a Screen dashboard inside
 *  the app fits there without scrolling (issue #923). It guesses first, then takes off whatever
 *  still makes the page scroll (the page's own padding), so it needs no numbers from the shell. */
export function useFillHeight(el: HTMLElement | null, on: boolean): number | undefined {
  const [height, setHeight] = useState<number>()
  useEffect(() => {
    if (!on || !el) return undefined
    let frame = 0
    const measure = () => {
      const footer = document.querySelector('.fb-status')?.getBoundingClientRect().height ?? 0
      const guess = Math.max(320, Math.floor(window.innerHeight - el.getBoundingClientRect().top - footer))
      setHeight(guess)
      frame = window.requestAnimationFrame(() => {
        const over = (document.scrollingElement?.scrollHeight ?? 0) - window.innerHeight
        if (over > 0) setHeight(Math.max(320, guess - over))
      })
    }
    frame = window.requestAnimationFrame(measure)
    window.addEventListener('resize', measure)
    return () => { window.cancelAnimationFrame(frame); window.removeEventListener('resize', measure) }
  }, [el, on])
  return on ? height : undefined
}
