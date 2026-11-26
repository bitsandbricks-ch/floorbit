import { useQuery } from '@tanstack/react-query'
import { get } from './client'

/** An address that sent to the agents but matches no inventory device (issue #1443). */
export interface UnknownSender {
  address: string
  /** What it calls itself: the syslog host name or the trap's sysName. */
  name: string
  kinds: Partial<Record<'syslog' | 'trap' | 'stream' | 'flow', number>>
  first: number
  last: number
  agents: string[]
  ignored: boolean
}

/** Under the inventory's key, so anything that changes the inventory asks again. */
export const unknownSendersKey = ['inventory', 'unknown-senders'] as const

export function useUnknownSenders() {
  return useQuery({
    queryKey: unknownSendersKey,
    queryFn: () => get<{ senders: UnknownSender[] }>('/api/inventory/unknown-senders'),
    refetchInterval: 60_000,
  })
}
