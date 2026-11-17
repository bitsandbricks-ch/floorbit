import { Alert, Button, Checkbox, Group, Modal, NumberInput, Select, SimpleGrid, Stack, TextInput } from '@mantine/core'
import { IconPrinter } from '@tabler/icons-react'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, patch, post } from '@/api/client'
import type { Cable } from '@/api/types'
import { EntitySelect } from '@/components/EntitySelect'

export type CableDraft = Pick<Cable, 'label' | 'switch' | 'port' | 'panel' | 'panel_port' | 'seat' | 'color' | 'note'> & { length_m: number | string; type: string; speed: string }
const TYPES = ['cat5e', 'cat6', 'cat6a', 'fiber-sm', 'fiber-mm', 'dac']
const SPEEDS = ['1', '10', '25', '40', '100']

const EMPTY: CableDraft = { label: '', switch: '', port: '', panel: '', panel_port: '', seat: '', color: '', note: '', length_m: '', type: '', speed: '' }

/** One cable: switch port, patch panel port and seat, each picked from what Floorbit knows (free
 *  ports only, unless asked), with type, speed, label and note. The Cables page and the floor plan's
 *  Edit mode both use it. ``onDone`` gets what changed, so the plan can offer undo. */
export function CableModal({ cable, canEdit, initial, onClose, onDone }: {
  cable: Cable | null; canEdit: boolean; initial?: Partial<CableDraft>; onClose: () => void
  onDone: (change: { saved?: Cable; removed?: Cable; before?: Cable | null }) => void
}) {
  const { t } = useTranslation()
  const imported = cable?.source === 'import'
  const readOnly = !canEdit || imported
  const [d, setD] = useState<CableDraft>(() => cable
    ? { ...cable, length_m: cable.length_m ?? '', type: cable.type ?? '', speed: cable.speed ? String(cable.speed) : '' }
    : { ...EMPTY, ...initial })
  const set = (k: keyof CableDraft) => (v: string | number) => setD((x) => ({ ...x, [k]: v }))
  const text = (k: keyof CableDraft) => ({
    value: String(d[k]), readOnly,
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => set(k)(e.currentTarget.value),
  })
  const save = useMutation({
    mutationFn: () => {
      const body = { ...d, length_m: d.length_m === '' ? null : d.length_m, speed: d.speed ? Number(d.speed) : null }
      return cable ? patch<Cable>(`/api/cables/${cable.id}`, body) : post<Cable>('/api/cables', body)
    },
    onSuccess: (saved) => onDone({ saved, before: cable }),
  })
  const remove = useMutation({ mutationFn: () => del(`/api/cables/${cable!.id}`), onSuccess: () => onDone({ removed: cable! }) })
  const [anyPort, setAnyPort] = useState(false)
  return (
    <Modal opened onClose={onClose} title={cable ? cable.label : t('cables.add')} size="lg">
      <Stack gap="sm">
        {imported && <Alert color="info">{t('cables.fromImport', { plugin: cable?.plugin ?? 'NetBox' })}</Alert>}
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          <EntitySelect kind="switches" label={t('cables.switch')} required readOnly={readOnly}
            value={d.switch} onChange={(v) => setD((x) => ({ ...x, switch: v, port: v === x.switch ? x.port : '' }))} />
          <EntitySelect kind="ports" switchName={d.switch} label={t('cables.port')} required readOnly={readOnly}
            value={d.port} onChange={set('port')} showUsed={anyPort} />
          <EntitySelect kind="panels" label={t('cables.panel')} readOnly={readOnly} placeholder={t('cables.panelPlaceholder')}
            value={d.panel} onChange={(v) => setD((x) => ({ ...x, panel: v, panel_port: v === x.panel ? x.panel_port : '' }))} />
          <EntitySelect kind="panel-ports" panelName={d.panel} label={t('cables.panelPort')} readOnly={readOnly}
            value={d.panel_port} onChange={set('panel_port')} showUsed={anyPort} />
          <EntitySelect kind="seats" label={t('cables.seat')} readOnly={readOnly} value={d.seat} onChange={set('seat')} />
          <TextInput label={t('cables.label')} placeholder={t('cables.labelPlaceholder')} {...text('label')} />
          <TextInput label={t('cables.color')} {...text('color')} />
          <NumberInput label={t('cables.length')} min={0.1} max={500} step={0.5} decimalScale={1} readOnly={readOnly}
            value={d.length_m} onChange={set('length_m')} />
          <Select label={t('cables.type')} clearable readOnly={readOnly} value={d.type || null} onChange={(v) => set('type')(v ?? '')}
            data={TYPES.map((v) => ({ value: v, label: t(`topology.types.${v}`) }))} />
          <Select label={t('cables.speed')} clearable readOnly={readOnly} value={d.speed || null} onChange={(v) => set('speed')(v ?? '')}
            data={SPEEDS.map((v) => ({ value: v, label: `${v}G` }))} />
        </SimpleGrid>
        <TextInput label={t('cables.note')} maxLength={200} {...text('note')} />
        {!readOnly && <Checkbox label={t('cables.anyPort')} checked={anyPort} onChange={(e) => setAnyPort(e.currentTarget.checked)} />}
        {(save.error || remove.error) && <Alert color="down" role="alert">{(save.error || remove.error)!.message}</Alert>}
        <Group justify="space-between">
          {cable ? (
            <Button variant="default" component="a" target="_blank" leftSection={<IconPrinter size={16} />}
              href={`/api/cables/labels.pdf?ids=${cable.id}`}>{t('cables.printOne')}</Button>
          ) : <span />}
          {!readOnly && (
            <Group gap="sm">
              {cable && <Button variant="subtle" color="down" loading={remove.isPending} onClick={() => remove.mutate()}>{t('cables.delete')}</Button>}
              <Button loading={save.isPending} disabled={!d.switch.trim() || !d.port.trim()} onClick={() => save.mutate()}>
                {t('cables.save')}
              </Button>
            </Group>
          )}
        </Group>
      </Stack>
    </Modal>
  )
}

