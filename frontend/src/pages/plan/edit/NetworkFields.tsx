import { Badge, Button, Group, Modal, NumberInput, Progress, SegmentedControl, Stack, Text, TextInput } from '@mantine/core'
import { IconPencil, IconRoute } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { PlanCable, PlanPanel } from '@/api/types'
import { type EntityOption, EntitySelect } from '@/components/EntitySelect'
import { nextName } from './tools'

const PORT_COUNTS = ['12', '24', '48']

/** A new patch panel where the plan was clicked: its name (the next free one) and how many ports. */
export function PlacePanelDialog({ opened, names, onClose, onCreate }: {
  opened: boolean; names: string[]; onClose: () => void; onCreate: (body: { name: string; ports: number }) => Promise<boolean>
}) {
  const { t } = useTranslation()
  if (!opened) return null
  return <PanelForm key={names.join('|')} names={names} onClose={onClose} onCreate={onCreate} title={t('plan.edit.panel.title')} />
}

function PanelForm({ names, onClose, onCreate, title }: {
  names: string[]; onClose: () => void; onCreate: (body: { name: string; ports: number }) => Promise<boolean>; title: string
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(() => (names.length ? nextName(names[names.length - 1], names) : 'PP-01'))
  const [ports, setPorts] = useState(24)
  const [busy, setBusy] = useState(false)
  const taken = names.some((n) => n.toLowerCase() === name.trim().toLowerCase())
  const submit = async () => {
    if (!name.trim() || taken) return
    setBusy(true)
    try {
      await onCreate({ name: name.trim(), ports })
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal opened onClose={onClose} title={title}>
      <form onSubmit={(e) => { e.preventDefault(); void submit() }}>
        <Stack gap="sm">
          <TextInput label={t('plan.edit.panel.name')} value={name} maxLength={40} required data-autofocus
            error={taken ? t('plan.edit.panel.taken') : undefined} onChange={(e) => setName(e.currentTarget.value)} />
          <div>
            <Text size="sm" fw={500} mb={4}>{t('plan.edit.panel.ports')}</Text>
            <Group gap="sm" wrap="nowrap" align="flex-start">
              <SegmentedControl value={PORT_COUNTS.includes(String(ports)) ? String(ports) : ''} onChange={(v) => setPorts(Number(v))}
                data={PORT_COUNTS.map((v) => ({ value: v, label: v }))} />
              <NumberInput aria-label={t('plan.edit.panel.ports')} min={1} max={96} w={90} value={ports} onChange={(v) => setPorts(Math.min(96, Math.max(1, Number(v) || 1)))} />
            </Group>
          </div>
          <Text size="xs" c="dimmed">{t('plan.edit.panel.help')}</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
            <Button type="submit" loading={busy} disabled={!name.trim() || taken}>{t('plan.edit.panel.place')}</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

/** A selected patch panel: how full it is, its port count, and which seat is on each port. */
export function PanelFields({ panel, onPorts }: { panel: PlanPanel; onPorts: (before: number, after: number) => Promise<void> }) {
  const { t } = useTranslation()
  const [ports, setPorts] = useState<number | null>(null)
  const list = useQuery({
    queryKey: qk.options('panel-ports', panel.name),
    queryFn: () => get<{ options: EntityOption[] }>(`/api/options/panel-ports?panel=${encodeURIComponent(panel.name)}`),
    staleTime: 10_000,
  })
  const save = () => { if (ports && ports !== panel.ports) void onPorts(panel.ports, ports).then(() => list.refetch()) }
  return (
    <>
      <div>
        <Group justify="space-between" mb={4}>
          <Text size="sm" fw={500}>{t('plan.edit.panel.usage', { used: panel.used, ports: panel.ports })}</Text>
          {panel.used >= panel.ports && <Badge color="warn" variant="light">{t('plan.edit.panel.full')}</Badge>}
        </Group>
        <Progress value={(panel.used / Math.max(1, panel.ports)) * 100} color={panel.used >= panel.ports ? 'warn' : 'bit'} size="sm" />
      </div>
      <NumberInput label={t('plan.edit.panel.ports')} min={1} max={96} value={ports ?? panel.ports} onChange={(v) => setPorts(Number(v) || null)}
        onBlur={save} onKeyDown={(e) => { if (e.key === 'Enter') save() }} />
      {!!list.data?.options.length && (
        <div className="fb-edit-ports" role="list" aria-label={t('plan.edit.panel.portList')}>
          {list.data.options.map((o) => (
            <span key={o.value} role="listitem" className={o.used ? 'used' : undefined} title={o.used ? t('ui.usedBy', { who: o.used }) : t('plan.edit.panel.free')}>
              <b>{o.value}</b>{o.used ? ` ${o.used}` : ''}
            </span>
          ))}
        </div>
      )}
    </>
  )
}

export type CableLook = 'straight' | 'square' | 'round'
export interface CableEnds { switch?: string; port?: string; seat?: string }

/** A selected cable: both its ends (switch and port, seat) picked right here, how it is drawn
 *  (straight, angled, rounded), back to the automatic route, and the full cable form. Its bends
 *  are dragged on the plan. */
export function CableFields({ cable, onEdit, onCorners, onReset, onEnds }: {
  cable: PlanCable; onEdit: () => void; onCorners: (corners: CableLook) => void; onReset: () => void
  onEnds: (change: CableEnds) => void
}) {
  const { t } = useTranslation()
  const r = cable.ref
  const imported = r.source === 'import'
  // A new switch needs its port before the cable can move there: kept here until the port is picked.
  const [sw, setSw] = useState<string | null>(null)
  const switchNow = sw ?? r.switch ?? ''
  return (
    <>
      <Stack gap="xs">
        <Text size="sm" fw={500}>{t('plan.edit.cable.ends')}</Text>
        <Group gap="xs" grow wrap="nowrap" align="flex-start">
          <EntitySelect kind="switches" size="xs" label={t('plan.edit.cable.switch')} readOnly={imported} value={switchNow}
            onChange={(v) => setSw(v && v !== r.switch ? v : null)} />
          <EntitySelect kind="ports" size="xs" switchName={switchNow} label={t('plan.edit.cable.port')} readOnly={imported}
            value={sw ? '' : r.port ?? ''} error={sw ? t('plan.edit.cable.pickPort') : undefined}
            onChange={(v) => { if (!v) return; onEnds(sw ? { switch: sw, port: v } : { port: v }); setSw(null) }} />
        </Group>
        {cable.via && <Text size="sm"><Text span c="dimmed">{t('plan.edit.cable.panel')}</Text> {cable.via}</Text>}
        <EntitySelect kind="seats" size="xs" label={t('plan.edit.cable.seat')} readOnly={imported} value={r.seat ?? ''}
          onChange={(v) => { if (v && v !== r.seat) onEnds({ seat: v }) }} />
        {imported && <Text size="xs" c="dimmed">{t('plan.edit.cable.imported')}</Text>}
      </Stack>
      <div>
        <Text size="sm" fw={500} mb={4}>{t('plan.edit.cable.look')}</Text>
        <SegmentedControl fullWidth value={cable.corners} onChange={(v) => onCorners(v as CableLook)} aria-label={t('plan.edit.cable.look')}
          data={[{ value: 'straight', label: t('plan.edit.cable.straight') }, { value: 'square', label: t('plan.edit.cable.square') },
            { value: 'round', label: t('plan.edit.cable.round') }]} />
      </div>
      <Text size="xs" c="dimmed">{t('plan.edit.cable.bendHelp')}</Text>
      {(cable.manual || cable.corners !== 'square') && <Button variant="default" leftSection={<IconRoute size={16} />} onClick={onReset}>{t('plan.edit.cable.auto')}</Button>}
      <Button variant="light" leftSection={<IconPencil size={16} />} onClick={onEdit}>{t('plan.edit.cable.edit')}</Button>
    </>
  )
}
