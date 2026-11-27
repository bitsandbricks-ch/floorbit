import { Alert, Anchor, Badge, Loader, Text, TextInput } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useFlows } from '@/api/queries'
import type { FlowMix, FlowsData } from '@/api/types'
import type { ViewProps } from '@/pages/monitoring/pages'
import { Card, DataTable, ErrorBanner } from '@bitsandbricks/ui'
import { bytes, mostly, total } from './format'
import { mixParts, useTrafficCategories } from '@/api/trafficCategories'
import { onPlan } from '../plan/links'
import { clock } from '@/lib/time'
import { TrafficServices } from './TrafficServices'
import { TrafficOwners } from './TrafficOwners'


/** One bar split by category, with the shares as its accessible name. */
export function MixBar({ mix, label, big }: { mix: FlowMix | undefined; label: string; big?: boolean }) {
  const { t } = useTranslation()
  const sum = total(mix)
  const parts = mixParts(mix, useTrafficCategories())
  const name = `${label}: ${parts.map((c) => `${c.label} ${Math.round((c.bytes / sum) * 100)} %`).join(', ')}`
  return (
    <div className={`fb-mix${big ? ' big' : ''}`} role="img" aria-label={sum ? name : `${label}: ${t('traffic.nothing')}`}>
      {parts.map((c) => <i key={c.id} style={{ width: `${(c.bytes / sum) * 100}%`, background: c.colour }} />)}
    </div>
  )
}

function Legend({ mix }: { mix: FlowMix | undefined }) {
  const sum = total(mix)
  return (
    <ul className="fb-mix-legend">
      {mixParts(mix, useTrafficCategories()).map((c) => (
        <li key={c.id}><i style={{ background: c.colour }} /> {c.label} <strong>{Math.round((c.bytes / sum) * 100)} %</strong>
          <span>{bytes(c.bytes)}</span></li>
      ))}
    </ul>
  )
}

function Seats({ seats }: { seats: NonNullable<FlowsData['seats']> }) {
  const { t } = useTranslation()
  const cats = useTrafficCategories()
  const [filter, setFilter] = useState('')
  const shown = seats.filter((s) => !filter || s.seat.toLowerCase().includes(filter.toLowerCase()))
  return (
    <Card heading={2} className="fb-wide" title={t('traffic.seats')} actions={<>
      <TextInput size="xs" placeholder={t('traffic.seatFilter')} aria-label={t('traffic.seatFilter')} value={filter}
        onChange={(e) => setFilter(e.currentTarget.value)} />
    </>}>
      <Text size="sm" c="dimmed" mb="xs">{t('traffic.seatsText')}</Text>
      <DataTable rows={shown} rowKey={(s) => s.seat} label={t('traffic.seats')} urlState={false} bare striped density="compact"
        defaultSort={{ id: 'volume', desc: true }}
        columns={[
          { id: 'seat', header: t('traffic.seat'), sort: (s) => s.seat, cell: (s) => <Anchor href={onPlan({ seat: s.seat })}>{s.seat}</Anchor> },
          { id: 'volume', header: t('traffic.volume'), descFirst: true, sort: (s) => s.bytes, cell: (s) => {
            const main = mostly(s.mix)
            return <>{bytes(s.bytes)}{main && <Text size="xs" c="dimmed">{t('traffic.mostly', { cat: cats.label(main) })}</Text>}</>
          } },
          { id: 'mix', header: t('traffic.mix'), width: '45%', cell: (s) => <MixBar mix={s.mix} label={s.seat} /> },
        ]} />
    </Card>
  )
}

function Board({ data, compact }: { data: FlowsData; compact: boolean }) {
  const { t } = useTranslation()
  const cats = useTrafficCategories()
  const services = data.services ?? []
  return (
    <div className="fb-stats">
      {!!data.anomalies?.length && (
        <Card heading={2} className="fb-wide" title={t('traffic.anomalies')}>
          <ul className="fb-flow-anomalies">
            {data.anomalies.map((a) => (
              <li key={a.id} className={a.kind}>
                <Badge variant="light" color={a.kind === 'rogue-dhcp' || a.kind === 'burst' ? 'down' : 'warn'} tt="none">{t(`traffic.kind.${a.kind}`)}</Badge>
                <span><strong>{a.title}</strong>{a.detail ? ` · ${a.detail}` : ''}{!a.seat && a.area ? ` · ${t('traffic.inArea', { area: a.area })}` : ''}</span>
                <span className="when">{t('traffic.since', { time: clock(a.first_seen) })}</span>
                {a.seat && <Anchor href={onPlan({ seat: a.seat })} size="sm">{t('traffic.show')}</Anchor>}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card heading={2} className="fb-wide" title={t('traffic.hall')}>
        <Text size="sm" c="dimmed" mb={4}>{t('traffic.lastHour', { volume: bytes(total(data.mix_hour)) })}</Text>
        <MixBar mix={data.mix_hour} label={t('traffic.hall')} big />
        <Legend mix={data.mix_hour} />
        <Text size="sm" c="dimmed" mt="sm" mb={4}>{t('traffic.lastDay', { volume: bytes(total(data.mix_day)) })}</Text>
        <MixBar mix={data.mix_day} label={t('traffic.day')} />
      </Card>

      {!compact && <Card heading={2} title={t('traffic.areas')}>
        <ul className="fb-flow-areas">
          {(data.areas ?? []).map((a) => (
            <li key={a.area}>
              <span className="name">{a.area}</span>
              <MixBar mix={a.mix} label={a.area} />
              <span className="value">{bytes(a.bytes)}</span>
            </li>
          ))}
        </ul>
        <Text size="xs" c="dimmed" mt={6}>{t('traffic.areasText')}</Text>
      </Card>}

      {compact ? (
        <Card heading={2} title={t('traffic.services')}>
          <ol className="fb-stats-top">
            {services.map((s) => (
              <li key={s.name}>
                <span className="name"><i className="fb-dotcat" style={{ background: cats.of(s.category).colour }} /> {s.name} <small>· {t('traffic.seatCount', { count: s.seats })}</small></span>
                <span className="value">{bytes(s.bytes)}</span>
              </li>
            ))}
          </ol>
        </Card>
      ) : <TrafficServices data={data} />}

      {!compact && <TrafficOwners data={data} />}

      {!compact && data.seats && <Seats seats={data.seats} />}
    </div>
  )
}

/** What the hall's traffic is made of, from NetFlow or IPFIX (issue #25). Aggregate only:
 *  nobody sees what a person visited. Small, the hall's mix and the services; opened up, everything. */
export default function TrafficView({ expanded }: ViewProps) {
  const { t } = useTranslation()
  const flows = useFlows()
  const data = flows.data
  return (
    <>
      <ErrorBanner error={flows.error} mb="md" />
      {data?.rules_error && <Alert color="warn" mb="md">{t('traffic.rulesError', { message: data.rules_error })}</Alert>}
      {flows.isPending || !data ? <Loader size="sm" aria-label={t('common.loading')} /> : !data.collector ? (
        <Alert color="gray" variant="light">{t('traffic.noCollector')} <Anchor href="https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/flows.md">docs/flows.md</Anchor></Alert>
      ) : (
        <>
          {expanded && (
            <Text size="sm" c="dimmed" mb="sm">
              {data.updated ? t('traffic.updated', { time: clock(data.updated) }) : ''}
              {data.stale ? ` · ${t('traffic.stale')}` : ''}
              {data.agent ? ` · ${t('traffic.viaAgent', { agent: data.agent })}` : ''}
              {' · '}{t('traffic.privacy', { days: data.retention_days ?? 7 })}
            </Text>
          )}
          <Board data={data} compact={!expanded} />
        </>
      )}
    </>
  )
}
