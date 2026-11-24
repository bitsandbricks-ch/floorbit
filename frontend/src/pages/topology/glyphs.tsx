import type { TopologyNode } from '@/api/types'
import { SwitchGlyph } from '../plan/SeatMap'

/** A device as the floor plan draws it (#1331): the plan's switch glyph for switches, and the same
 *  24x16 body with its own mark for routers and firewalls. The body takes the plan's status
 *  colours (``.fb-plan .sw-<status> .body``); down is the red body with a white cross everywhere,
 *  so it doesn't rely on colour. Centred on 0,0. */
export function DeviceGlyph({ role, status }: { role: string; status: TopologyNode['status'] }) {
  if (role !== 'router' && role !== 'firewall') return <SwitchGlyph status={status} />
  const down = status === 'offline'
  return (
    <>
      {role === 'router'
        ? <rect className="body" x={-15} y={-9} width={30} height={18} rx={9} />
        : <rect className="body" x={-12} y={-8} width={24} height={16} rx={2} />}
      {down
        ? <path className="cross" d="M-3.5 -4.5l7 9M3.5 -4.5l-7 9" />
        : role === 'router'
          ? <path className="mark" d="M-7 -3h12l-3 -3M7 3h-12l3 3" />
          : <path className="mark" d="M-12 0h24M-4 -8v8M4 0v8M-8 0v8M8 -8v8" />}
    </>
  )
}

/** An internet line: a cloud, so it doesn't read as one more switch. Centred on 0,0. */
export function UplinkGlyph() {
  return <path className="cloud" d="M-11 8h22a7 7 0 0 0 1-14a9 9 0 0 0-17-2a7 7 0 0 0-6 16z" />
}
