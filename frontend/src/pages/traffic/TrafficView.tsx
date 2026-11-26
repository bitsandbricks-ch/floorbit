import { Alert, Anchor, Badge, Loader, Text, TextInput } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useFlows } from '@/api/queries'
import type { FlowMix, FlowsData } from '@/api/types'
import type { ViewProps } from '@/pages/monitoring/pages'
import { DataTable, ErrorBanner } from '@bitsandbricks/ui'
import { bytes, CATEGORIES, mostly, total } from './format'
import { onPlan } from '../plan/links'
import { clock } from '@/lib/time'
import { Panel } from '@/components/ui'
import { TrafficServices } from './TrafficServices'
import { TrafficOwners } from './TrafficOwners'


/** One bar split by category, with the shares as its accessible name. */
function MixBar({ mix, label, big }: { mix: FlowMix | undefined; label: string; big?: boolean }) {
  const { t } = useTranslation()
  const sum = total(mix)
  const parts = CATEGORIES.filter((c) => (mix?.[c] ?? 0) > 0)
  const name = `${label}: ${parts.map((c) => `${t(`traffic.cat.${c}`)} ${Math.round(((mix?.[c] ?? 0) / sum) * 100)} %`).join(', ')}`
  return (
    <div className={`fb-mix${big ? ' big' : ''}`} role="img" aria-label={sum ? name : `${label}: ${t('traffic.nothing')}`}>
      {parts.map((c) => <i key={c} className={`cat-${c}`} style={{ width: `${((mix?.[c] ?? 0) / sum) * 100}%` }} />)}
    </div>
  )
}

function Legend({ mix }: { mix: FlowMix | undefined }) {
  const { t } = useTranslation()
  const sum = total(mix)
  return (
    <ul className="fb-mix-legend">
      {CATEGORIES.filter((c) => (mix?.[c] ?? 0) > 0).map((c) => (
        <li key={c}><i className={`cat-${c}`} /> {t(`traffic.cat.${c}`)} <strong>{Math.round(((mix?.[c] ?? 0) / sum) * 100)} %</strong>
          <span>{bytes(mix?.[c])}</span></li>
      ))}
    </ul>
  )
}

function Seats({ seats }: { seats: NonNullable<FlowsData['seats']> }) {
  const { t } = useTranslation()
  const [filter, setFilter] = useState('')
  const shown = seats.filter((s) => !filter || s.seat.toLowerCase().includes(filter.toLowerCase()))
  return (
    <Panel className="fb-wide" titleId="traffic-seats" title={t('traffic.seats')} actions={<>
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
            return <>{bytes(s.bytes)}{main && <Text size="xs" c="dimmed">{t('traffic.mostly', { cat: t(`traffic.cat.${main}`) })}</Text>}</>
          } },
          { id: 'mix', header: t('traffic.mix'), width: '45%', cell: (s) => <MixBar mix={s.mix} label={s.seat} /> },
        ]} />
    </Panel>
  )
}

function Board({ data, compact }: { data: FlowsData; compact: boolean }) {
  const { t } = useTranslation()
  const services = data.services ?? []
  return (
    <div className="fb-stats">
      {!!data.anomalies?.length && (
        <Panel className="fb-wide" titleId="traffic-anomalies" title={t('traffic.anomalies')}>
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
        </Panel>
      )}

      <Panel className="fb-wide" titleId="traffic-mix" title={t('traffic.hall')}>
        <Text size="sm" c="dimmed" mb={4}>{t('traffic.lastHour', { volume: bytes(total(data.mix_hour)) })}</Text>
        <MixBar mix={data.mix_hour} label={t('traffic.hall')} big />
        <Legend mix={data.mix_hour} />
        <Text size="sm" c="dimmed" mt="sm" mb={4}>{t('traffic.lastDay', { volume: bytes(total(data.mix_day)) })}</Text>
        <MixBar mix={data.mix_day} label={t('traffic.day')} />
      </Panel>

      {!compact && <Panel titleId="traffic-areas" title={t('traffic.areas')}>
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
      </Panel>}

      {compact ? (
        <Panel titleId="traffic-services" title={t('traffic.services')}>
          <ol className="fb-stats-top">
            {services.map((s) => (
              <li key={s.name}>
                <span className="name"><i className={`fb-dotcat cat-${s.category}`} /> {s.name} <small>· {t('traffic.seatCount', { count: s.seats })}</small></span>
                <span className="value">{bytes(s.bytes)}</span>
              </li>
            ))}
          </ol>
        </Panel>
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
