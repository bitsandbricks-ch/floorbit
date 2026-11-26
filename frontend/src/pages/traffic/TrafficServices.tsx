import { Badge, Group, Text } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { FlowService, FlowsData } from '@/api/types'
import { DataTable, PanelField, PanelSection, SidePanel, Sparkline, type DataColumn } from '@bitsandbricks/ui'
import { Panel } from '@/components/ui'
import { clock } from '@/lib/time'
import { bytes, trendOf } from './format'
import { useTrafficCategories } from '@/api/trafficCategories'

/** What the hall's traffic goes to, per application (issue #1481, crew view A): seats, down, up and
 *  the last hours. Aggregate only: a service and each of its blocks need five seats or more. */
export function TrafficServices({ data }: { data: FlowsData }) {
  const { t } = useTranslation()
  const cats = useTrafficCategories()
  const services = data.services ?? []
  const [open, setOpen] = useState<string | null>(null)
  const index = services.findIndex((s) => s.name === open)
  const current = index >= 0 ? services[index] : null
  const columns: DataColumn<FlowService>[] = [
    { id: 'name', header: t('traffic.svc.application'), sort: (s) => s.name, cell: (s) => (
      <Group gap={6} wrap="nowrap">
        <span>{s.name}</span>
        <Badge size="xs" variant="light" color="gray" tt="none">{cats.label(s.category)}</Badge>
      </Group>
    ) },
    { id: 'seats', header: t('traffic.svc.seats'), numeric: true, descFirst: true, sort: (s) => s.seats, cell: (s) => s.seats },
    { id: 'down', header: t('traffic.svc.down'), numeric: true, descFirst: true, sort: (s) => s.down ?? s.bytes,
      cell: (s) => (s.down == null ? bytes(s.bytes) : bytes(s.down)) },
    { id: 'up', header: t('traffic.svc.up'), numeric: true, descFirst: true, hideOnPhone: true, sort: (s) => s.up ?? 0,
      cell: (s) => (s.up == null ? '–' : bytes(s.up)) },
    { id: 'trend', header: t('traffic.svc.trend'), hideOnPhone: true, cell: (s) => (
      <span aria-label={t('traffic.svc.trendLabel', { name: s.name })} role="img" style={{ display: 'inline-block', width: 80 }}>
        <Sparkline points={trendOf(s, data.updated).map((p) => p.bytes)} min={0} />
      </span>
    ) },
  ]
  return (
    <Panel className="fb-wide" titleId="traffic-services" title={t('traffic.services')}>
      <DataTable rows={services} columns={columns} rowKey={(s) => s.name} label={t('traffic.services')} urlState={false}
        bare density="compact" defaultSort={{ id: 'down', desc: true }}
        onRowClick={(s) => setOpen(s.name)}
        selected={open} />
      <Text size="xs" c="dimmed" mt={6}>
        {t('traffic.servicesText', { count: data.min_seats ?? 5, volume: bytes(data.other_services) })}
      </Text>
      {current && (
        <ServicePanel key={current.name} service={current} data={data} onClose={() => setOpen(null)}
          onPrev={index > 0 ? () => setOpen(services[index - 1].name) : undefined}
          onNext={index < services.length - 1 ? () => setOpen(services[index + 1].name) : undefined} />
      )}
    </Panel>
  )
}

function ServicePanel({ service: s, data, onClose, onPrev, onNext }: {
  service: FlowService; data: FlowsData; onClose: () => void; onPrev?: () => void; onNext?: () => void
}) {
  const { t } = useTranslation()
  const cats = useTrafficCategories()
  const blocks = Object.entries(s.areas ?? {}).sort((a, b) => b[1] - a[1])
  const named = blocks.reduce((sum, [, v]) => sum + v, 0)
  return (
    <SidePanel onClose={onClose} onPrev={onPrev} onNext={onNext} padded={false} title={s.name}
      eyebrow={`${cats.label(s.category)} · ${t('traffic.seatCount', { count: s.seats })}`}>
      <PanelSection>
        <PanelField label={t('traffic.svc.down')}>{s.down == null ? bytes(s.bytes) : bytes(s.down)}</PanelField>
        <PanelField label={t('traffic.svc.up')}>{s.up == null ? '–' : bytes(s.up)}</PanelField>
      </PanelSection>
      <PanelSection label={t('traffic.svc.blocks')}>
        {blocks.length ? blocks.map(([area, v]) => <PanelField key={area} label={area}>{bytes(v)}</PanelField>) : (
          <Text size="sm" c="dimmed">{t('traffic.svc.noBlocks')}</Text>
        )}
        {blocks.length > 0 && s.bytes > named && (
          <PanelField label={t('traffic.svc.otherBlocks')}>{bytes(s.bytes - named)}</PanelField>
        )}
      </PanelSection>
      <PanelSection label={t('traffic.svc.hours')}>
        {trendOf(s, data.updated).slice().reverse().map((p) => (
          <PanelField key={p.t} label={clock(p.t)}>{bytes(p.bytes)}</PanelField>
        ))}
      </PanelSection>
      <PanelSection>
        <Text size="xs" c="dimmed">{t('traffic.svc.privacy', { count: data.min_seats ?? 5 })}</Text>
      </PanelSection>
    </SidePanel>
  )
}
