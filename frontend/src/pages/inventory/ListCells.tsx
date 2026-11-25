import { Text, Tooltip } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { StateStrip, type StateCell } from '@bitsandbricks/ui'
import type { Device } from '@/api/types'
import { linkSpeed } from './listColumns'

/** The inventory list's Uplink, Last 24 h and Agent columns (issue #981): what the one list call
 *  brings per device, drawn with the shared pieces. */

/** "10G", amber "1G of 10G" when slower than planned, red "down". */
export function UplinkCell({ d }: { d: Device }) {
  const { t } = useTranslation()
  const u = d.uplink
  if (!u) return <Text span c="dimmed">–</Text>
  const where = t('inventory.uplink.where', { port: u.port, peer: u.peer, peerPort: u.peer_port })
  const speed = u.speed_bps != null ? linkSpeed(u.speed_bps) : null
  const text = u.state === 'down' ? t('inventory.uplink.down')
    : u.issue === 'slow' && speed && u.planned_gbps ? t('inventory.uplink.slow', { speed, planned: `${u.planned_gbps}G` })
      : speed ?? (u.planned_gbps ? `${u.planned_gbps}G` : '–')
  const tone = u.state === 'down' ? 'fb-tone-err' : u.issue === 'slow' ? 'fb-tone-warn' : undefined
  return (
    <Tooltip label={where}>
      <Text span size="sm" ff="monospace" className={tone}>{text}</Text>
    </Tooltip>
  )
}

/** One block per hour, oldest left: green, amber when down for part of it, red for half or more. */
export function LastDayCell({ d }: { d: Device }) {
  const { t } = useTranslation()
  const hours = d.last_day
  if (!hours) return <StateStrip cells={Array.from({ length: 24 }, () => ({ tone: 'none' as const }))} label={t('inventory.lastDay.none')} />
  const cells: StateCell[] = hours.map((down, i) => {
    const ago = hours.length - i
    const tone = down >= 1800 ? 'err' : down > 0 ? 'warn' : 'ok'
    return { tone, title: down ? t('inventory.lastDay.down', { ago, minutes: Math.max(1, Math.round(down / 60)) }) : t('inventory.lastDay.up', { ago }) }
  })
  const bad = hours.filter((s) => s > 0).length
  return <StateStrip cells={cells} label={t('inventory.lastDay.label', { count: bad })} />
}
