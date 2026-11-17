import { useCallback, useRef, useState } from 'react'

/** One change the editor can take back: both ways call the server. */
export interface Step {
  label: string
  undo: () => Promise<unknown>
  redo: () => Promise<unknown>
}

interface Stacks { past: Step[]; future: Step[] }
const LIMIT = 100

/** Undo and redo for the editor, like the older editor's (static/js/editor/core.js pushHistory).
 *  A step that fails to undo or redo stays where it was, so a retry can try again. */
export function useHistory() {
  const [stacks, setStacks] = useState<Stacks>({ past: [], future: [] })
  // The callbacks run after awaits, so they read the latest stacks from here, not from a render.
  const live = useRef<Stacks>(stacks)
  const busy = useRef(false)
  const write = useCallback((next: Stacks) => { live.current = next; setStacks(next) }, [])

  const push = useCallback((step: Step) => {
    write({ past: [...live.current.past.slice(-(LIMIT - 1)), step], future: [] })
  }, [write])

  const run = useCallback(async (way: 'undo' | 'redo') => {
    if (busy.current) return null
    const from = way === 'undo' ? live.current.past : live.current.future
    const step = from[from.length - 1]
    if (!step) return null
    busy.current = true
    try {
      await step[way]()
      const { past, future } = live.current
      write(way === 'undo'
        ? { past: past.slice(0, -1), future: [...future, step] }
        : { past: [...past, step], future: future.slice(0, -1) })
      return step
    } finally {
      busy.current = false
    }
  }, [write])

  return {
    push,
    undo: useCallback(() => run('undo'), [run]),
    redo: useCallback(() => run('redo'), [run]),
    canUndo: stacks.past.length > 0,
    canRedo: stacks.future.length > 0,
    nextUndo: stacks.past[stacks.past.length - 1]?.label,
    nextRedo: stacks.future[stacks.future.length - 1]?.label,
  }
}
