import { useEffect, type RefObject } from 'react'

/** Closes a menu on Escape or a press outside ``box``. */
export function useCloseOutside(open: boolean, setOpen: (o: boolean) => void, box: RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    if (!open) return
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent && e.key !== 'Escape') return
      if (e.target instanceof Node && box.current?.contains(e.target) && !(e instanceof KeyboardEvent)) return
      setOpen(false)
    }
    document.addEventListener('keydown', close)
    document.addEventListener('pointerdown', close)
    return () => {
      document.removeEventListener('keydown', close)
      document.removeEventListener('pointerdown', close)
    }
  }, [open, setOpen, box])
}
