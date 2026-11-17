import { Badge, Group, ScrollArea, Stack, Tabs, Text, UnstyledButton } from '@mantine/core'
import { IconAlertTriangle, IconList, IconStack2 } from '@tabler/icons-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { SeatViewData } from '@/api/types'
import { Attribution } from '@/components/Attribution'
import { type LayerId, type LayerState } from './layers'
import { LayersBody, type LayerLegends } from './LayersPanel'
import { seatOrder } from './model'
import type { SideTab } from './side'


/** The plan's docked right panel, like a map editor's: Layers, Problems and Items while nothing is
 *  open; the open seat, block or switch (``inspector``) takes its place and closing it comes back. */
export function SidePanel({ data, tab, onTab, layers, onLayers, available, inspector, onSeat, onBlock, onSwitch, legends }: {
  data: SeatViewData; tab: SideTab; onTab: (t: SideTab) => void
  layers: LayerState; onLayers: (next: LayerState) => void; available: Record<LayerId, boolean>
  inspector: ReactNode; onSeat: (s: string) => void; onBlock: (b: string) => void; onSwitch: (w: string) => void
  /** What each layer that is on draws, under its switch. */
  legends?: LayerLegends
}) {
  const { t } = useTranslation()
  if (inspector) return <aside className="fb-ws-panel" aria-label={t('plan.side.label')}>{inspector}</aside>
  const seats = Object.entries(data.seats)
  const problems = seats.filter(([, s]) => s.problems).map(([n]) => n).sort(seatOrder)
  const offline = seats.filter(([, s]) => s.state === 'offline' && !s.problems).map(([n]) => n).sort(seatOrder)
  const isDown = (w: { status: string }) => w.status === 'offline'
  const down = data.switches.filter(isDown).length
  return (
    <aside className="fb-ws-panel tabs" aria-label={t('plan.side.label')}>
      <Tabs value={tab} onChange={(v) => v && onTab(v as SideTab)} keepMounted={false} className="fb-side-tabs">
        <Tabs.List grow>
          <Tabs.Tab value="layers" leftSection={<IconStack2 size={14} />}>{t('plan.side.layers')}</Tabs.Tab>
          {/* The count goes in the label: the tab's rightSection is only an icon wide and cuts it off. */}
          <Tabs.Tab value="problems" leftSection={<IconAlertTriangle size={14} />}>
            {t('plan.side.problems')}{problems.length + down ? <Badge size="xs" color="down" ml={6}>{problems.length + down}</Badge> : null}</Tabs.Tab>
          <Tabs.Tab value="items" leftSection={<IconList size={14} />}>{t('plan.side.items')}</Tabs.Tab>
        </Tabs.List>
        <ScrollArea className="fb-side-body" type="auto">
          <Tabs.Panel value="layers" p="md">
            <LayersBody state={layers} onChange={onLayers} available={available} legends={legends} />
          </Tabs.Panel>
          <Tabs.Panel value="problems" p="md">
            <Stack gap="md">
              {!problems.length && !offline.length && !down && <Text size="sm" c="dimmed">{t('plan.side.allGood')}</Text>}
              {down > 0 && (
                <Section title={t('plan.side.switchesDown', { count: down })}>
                  {data.switches.filter(isDown).map((w) => (
                    <Row key={w.id} onClick={() => onSwitch(w.name)} name={w.name} detail={t(`plan.state.${w.status}`, { defaultValue: w.status })} bad />
                  ))}
                </Section>
              )}
              {problems.length > 0 && (
                <Section title={t('plan.side.withProblems', { count: problems.length })}>
                  {problems.map((s) => <Row key={s} onClick={() => onSeat(s)} name={s} detail={t('plan.problemsN', { count: data.seats[s].problems ?? 0 })} bad />)}
                </Section>
              )}
              {offline.length > 0 && (
                <Section title={t('plan.side.offline', { count: offline.length })}>
                  {offline.map((s) => <Row key={s} onClick={() => onSeat(s)} name={s} detail={t('plan.state.offline')} />)}
                </Section>
              )}
            </Stack>
          </Tabs.Panel>
          <Tabs.Panel value="items" p="md">
            <Stack gap="md">
              <Section title={t('plan.side.blocks', { count: data.blocks.length })}>
                {data.blocks.map((b) => (
                  <Row key={b.name} onClick={() => onBlock(b.name)} name={t('plan.side.block', { name: b.name })}
                    detail={`${b.online}/${b.seats}${b.problems ? ` · ! ${b.problems}` : ''}`} bad={b.problems > 0} />
                ))}
              </Section>
              <Section title={t('plan.side.switches', { count: data.switches.length })}>
                {[...data.switches].sort((a, b) => a.name.localeCompare(b.name)).map((w) => (
                  <Row key={w.id} onClick={() => onSwitch(w.name)} name={w.name} detail={t(`plan.state.${w.status}`, { defaultValue: w.status })} bad={isDown(w)} />
                ))}
              </Section>
            </Stack>
          </Tabs.Panel>
        </ScrollArea>
      </Tabs>
      <div className="fb-side-foot"><Attribution compact /></div>
    </aside>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <Text size="xs" fw={700} tt="uppercase" c="dimmed" mb={4}>{title}</Text>
      <Stack gap={0} role="list">{children}</Stack>
    </div>
  )
}

function Row({ name, detail, onClick, bad = false }: { name: string; detail: string; onClick: () => void; bad?: boolean }) {
  return (
    <div role="listitem">
      <UnstyledButton className="fb-side-row" onClick={onClick}>
        <Group justify="space-between" wrap="nowrap" gap="xs">
          <Text size="sm" fw={500} truncate>{name}</Text>
          <Text size="xs" c={bad ? 'down' : 'dimmed'} truncate>{detail}</Text>
        </Group>
      </UnstyledButton>
    </div>
  )
}
