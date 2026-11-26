import type { WifiAp, WifiData } from '@/api/types'
import { loadColor } from '../wifi/colors'

const REACH = 140   // most of an AP's circle, in plan units (floorbit/blueprints/wifi.py)

/** Highest load over an AP's radios: the busiest band decides how it feels on the floor. */
function load(ap: WifiAp): number | null {
  const loads = ap.radios.map((r) => r.utilization).filter((u): u is number => u != null)
  return loads.length ? Math.max(...loads) : null
}

/** The Wi-Fi layer: each access point on this hall's plan, its rough coverage, coloured by load.
 *  Counts only, like the Wi-Fi page (issue #98). */
export function WifiLayer({ wifi, idPrefix }: { wifi: WifiData; idPrefix: string }) {
  const aps = wifi.aps.filter((a) => a.on_plan && a.px != null && a.py != null)
  if (!aps.length) return null
  const color = (ap: WifiAp) => (ap.status === 'down' ? 'var(--bnb-err)' : loadColor(load(ap), wifi.thresholds.busy))
  return (
    <g className="wifi-layer">
      <defs>
        {aps.map((ap, i) => (
          <radialGradient key={ap.name} id={`${idPrefix}-ap-${i}`}>
            <stop offset="0%" style={{ stopColor: color(ap), stopOpacity: 0.4 }} />
            <stop offset="100%" style={{ stopColor: color(ap), stopOpacity: 0 }} />
          </radialGradient>
        ))}
      </defs>
      {aps.map((ap, i) => ap.status === 'up' && (
        <circle key={ap.name} className="cover" cx={ap.px!} cy={ap.py!} r={REACH} fill={`url(#${idPrefix}-ap-${i})`} />
      ))}
      {aps.map((ap) => (
        <g key={ap.name} className={ap.status === 'down' ? 'ap down' : 'ap'} transform={`translate(${ap.px} ${ap.py})`}>
          <circle r={11} style={{ fill: color(ap) }} />
          <title>{`${ap.name}: ${ap.status === 'down' ? '✕' : `${ap.clients} · ${load(ap) ?? '?'} %`}`}</title>
        </g>
      ))}
    </g>
  )
}
