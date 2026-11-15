import { useEffect, useState } from 'react'

/** Now in unix seconds, ticking every 30 s, for labels that change with the clock alone. */
export function useNowSeconds() {
  const [now, setNow] = useState(() => Date.now() / 1000)
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now() / 1000), 30_000)
    return () => window.clearInterval(id)
  }, [])
  return now
}
