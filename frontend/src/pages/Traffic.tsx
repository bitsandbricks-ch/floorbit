import { Alert, Anchor, Badge, Button, Group, Loader, Table, Text, TextInput } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useFeature, useFlows } from '@/api/queries'
import type { FlowMix, FlowsData } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { bytes, CATEGORIES, mostly, total } from './traffic/format'

const clock = (ts: number) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

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
  const shown = seats.filter((s) => !filter || s.seat.toLowerCase().includes(filter.toLowerCase())).slice(0, 25)
  return (
    <section className="fb-stats-panel wide" aria-labelledby="traffic-seats">
      <Group justify="space-between" mb={6}>
        <h2 id="traffic-seats">{t('traffic.seats')}</h2>
        <TextInput size="xs" placeholder={t('traffic.seatFilter')} aria-label={t('traffic.seatFilter')} value={filter}
          onChange={(e) => setFilter(e.currentTarget.value)} />
      </Group>
      <Text size="sm" c="dimmed" mb="xs">{t('traffic.seatsText')}</Text>
      <Table striped withRowBorders={false} verticalSpacing={4}>
        <Table.Thead><Table.Tr><Table.Th>{t('traffic.seat')}</Table.Th><Table.Th>{t('traffic.volume')}</Table.Th><Table.Th>{t('traffic.mix')}</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {shown.map((s) => {
            const main = mostly(s.mix)
            return (
              <Table.Tr key={s.seat}>
                <Table.Td><Anchor href={`/?seat=${encodeURIComponent(s.seat)}`}>{s.seat}</Anchor></Table.Td>
                <Table.Td style={{ whiteSpace: 'nowrap' }}>{bytes(s.bytes)}{main && <Text span size="xs" c="dimmed"> · {t('traffic.mostly', { cat: t(`traffic.cat.${main}`) })}</Text>}</Table.Td>
                <Table.Td style={{ width: '45%' }}><MixBar mix={s.mix} label={s.seat} /></Table.Td>
              </Table.Tr>
            )
          })}
        </Table.Tbody>
      </Table>
    </section>
  )
}

function Board({ data }: { data: FlowsData }) {
  const { t } = useTranslation()
  const services = data.services ?? []
  return (
    <div className="fb-stats">
      {!!data.anomalies?.length && (
        <section className="fb-stats-panel wide" aria-labelledby="traffic-anomalies">
          <h2 id="traffic-anomalies">{t('traffic.anomalies')}</h2>
          <ul className="fb-flow-anomalies">
            {data.anomalies.map((a) => (
              <li key={a.id} className={a.kind}>
                <Badge variant="light" color={a.kind === 'rogue-dhcp' || a.kind === 'burst' ? 'down' : 'warn'} tt="none">{t(`traffic.kind.${a.kind}`)}</Badge>
                <span><strong>{a.title}</strong>{a.detail ? ` · ${a.detail}` : ''}{!a.seat && a.area ? ` · ${t('traffic.inArea', { area: a.area })}` : ''}</span>
                <span className="when">{t('traffic.since', { time: clock(a.first_seen) })}</span>
                {a.seat && <Anchor href={`/?seat=${encodeURIComponent(a.seat)}`} size="sm">{t('traffic.show')}</Anchor>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="fb-stats-panel wide" aria-labelledby="traffic-mix">
        <h2 id="traffic-mix">{t('traffic.hall')}</h2>
        <Text size="sm" c="dimmed" mb={4}>{t('traffic.lastHour', { volume: bytes(total(data.mix_hour)) })}</Text>
        <MixBar mix={data.mix_hour} label={t('traffic.hall')} big />
        <Legend mix={data.mix_hour} />
        <Text size="sm" c="dimmed" mt="sm" mb={4}>{t('traffic.lastDay', { volume: bytes(total(data.mix_day)) })}</Text>
        <MixBar mix={data.mix_day} label={t('traffic.day')} />
      </section>

      <section className="fb-stats-panel" aria-labelledby="traffic-areas">
        <h2 id="traffic-areas">{t('traffic.areas')}</h2>
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
      </section>

      <section className="fb-stats-panel" aria-labelledby="traffic-services">
        <h2 id="traffic-services">{t('traffic.services')}</h2>
        <ol className="fb-stats-top">
          {services.map((s) => (
            <li key={s.name}>
              <span className="name"><i className={`fb-dotcat cat-${s.category}`} /> {s.name} <small>· {t('traffic.seatCount', { count: s.seats })}</small></span>
              <span className="value">{bytes(s.bytes)}</span>
            </li>
          ))}
        </ol>
        <Text size="xs" c="dimmed" mt={6}>
          {t('traffic.servicesText', { count: data.min_seats ?? 5, volume: bytes(data.other_services) })}
        </Text>
      </section>

      {data.seats && <Seats seats={data.seats} />}
    </div>
  )
}

/** What the hall's traffic is made of, from NetFlow or IPFIX (issue #25). Aggregate only:
 *  nobody sees what a person visited. */
export default function Traffic() {
  const { t } = useTranslation()
  const flows = useFlows()
  const dnsOn = useFeature('dns')
  const gamesOn = useFeature('games')
  const data = flows.data
  return (
    <Layout title={t('traffic.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('traffic.title')} desc={t('traffic.intro')}
        actions={
          <Group gap="xs">
            {gamesOn && <Button variant="default" component="a" href="/games">{t('traffic.games')}</Button>}
            {dnsOn && <Button variant="default" component="a" href="/dns">{t('traffic.dns')}</Button>}
          </Group>
        } />
      {flows.error && <Alert color="down" role="alert" mb="md">{t('common.error', { message: flows.error.message })}</Alert>}
      {data?.rules_error && <Alert color="warn" mb="md">{t('traffic.rulesError', { message: data.rules_error })}</Alert>}
      {flows.isPending || !data ? <Loader size="sm" /> : !data.collector ? (
        <Alert color="gray" variant="light">{t('traffic.noCollector')} <Anchor href="https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/flows.md">docs/flows.md</Anchor></Alert>
      ) : (
        <>
          <Text size="sm" c="dimmed" mb="sm">
            {data.updated ? t('traffic.updated', { time: clock(data.updated) }) : ''}
            {data.stale ? ` · ${t('traffic.stale')}` : ''}
            {' · '}{t('traffic.privacy', { days: data.retention_days ?? 7 })}
          </Text>
          <Board data={data} />
        </>
      )}
    </Layout>
  )
}
