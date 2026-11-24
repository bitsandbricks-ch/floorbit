import { useEffect } from 'react'

/** While something is unsaved, closing or reloading the tab asks first (#993). The browser shows
 *  its own question; pages only say when there is something to lose. */
export function useLeaveWarning(unsaved: boolean) {
  useEffect(() => {
    if (!unsaved) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [unsaved])
}
