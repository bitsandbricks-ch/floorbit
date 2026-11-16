import { Button, Checkbox, Group, Modal, ScrollArea, SegmentedControl, Stack, Text, TextInput } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { nextSwitchName } from './tools'

export interface InventorySwitch { id: string; name: string; placed: boolean; source: string; netbox_status?: string }
export type SwitchPick = { ids: string[] } | { name: string }

/** Where the Switch tool was clicked: put switches from the inventory there (several at once in
 *  a small grid), or make one by hand. */
export function PlaceSwitchDialog({ opened, onClose, onPlace }: {
  opened: boolean; onClose: () => void; onPlace: (pick: SwitchPick) => Promise<boolean>
}) {
  const all = useQuery({ queryKey: qk.switches, queryFn: () => get<InventorySwitch[]>('/api/switches'), enabled: opened, staleTime: 5_000 })
  if (!opened || !all.data) return null
  return <SwitchForm list={all.data} onClose={onClose} onPlace={onPlace} />
}

function SwitchForm({ list, onClose, onPlace }: { list: InventorySwitch[]; onClose: () => void; onPlace: (pick: SwitchPick) => Promise<boolean> }) {
  const { t } = useTranslation()
  const free = list.filter((s) => !s.placed && s.source !== 'manual')
  const [tab, setTab] = useState(free.length ? 'inventory' : 'new')
  const [filter, setFilter] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [name, setName] = useState(() => nextSwitchName(list.map((s) => s.name), list.filter((s) => s.source === 'manual').length))
  const [busy, setBusy] = useState(false)
  const shown = free.filter((s) => s.name.toLowerCase().includes(filter.trim().toLowerCase()))
  const ready = tab === 'inventory' ? picked.length > 0 : !!name.trim()
  const submit = async () => {
    if (!ready) return
    setBusy(true)
    try {
      await onPlace(tab === 'inventory' ? { ids: picked } : { name: name.trim() })
    } finally {
      setBusy(false)
    }
  }
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))
  return (
    <Modal opened onClose={onClose} title={t('plan.edit.switch.title')}>
      <form onSubmit={(e) => { e.preventDefault(); void submit() }}>
        <Stack gap="sm">
          <SegmentedControl fullWidth value={tab} onChange={setTab}
            data={[{ value: 'inventory', label: t('plan.edit.switch.inventory', { count: free.length }) }, { value: 'new', label: t('plan.edit.switch.new') }]} />
          {tab === 'inventory' ? (
            <>
              <TextInput placeholder={t('plan.edit.switch.filter')} value={filter} onChange={(e) => setFilter(e.currentTarget.value)} data-autofocus />
              {shown.length ? (
                <ScrollArea.Autosize mah={280}>
                  <Stack gap={6} role="list" aria-label={t('plan.edit.switch.inventoryList')}>
                    {shown.map((s) => (
                      <Group key={s.id} justify="space-between" wrap="nowrap" role="listitem">
                        <Checkbox label={s.name} checked={picked.includes(s.id)} onChange={() => toggle(s.id)} />
                        {s.netbox_status && <Text size="xs" c="dimmed">{s.netbox_status}</Text>}
                      </Group>
                    ))}
                  </Stack>
                </ScrollArea.Autosize>
              ) : (
                <Text size="sm" c="dimmed">{t(filter ? 'plan.edit.switch.noneMatch' : 'plan.edit.switch.noneLeft')}</Text>
              )}
            </>
          ) : (
            <>
              <TextInput label={t('plan.edit.switch.name')} value={name} maxLength={64} required data-autofocus onChange={(e) => setName(e.currentTarget.value)} />
              <Text size="xs" c="dimmed">{t('plan.edit.switch.newHelp')}</Text>
            </>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
            <Button type="submit" loading={busy} disabled={!ready}>
              {tab === 'inventory' ? t('plan.edit.switch.place', { count: Math.max(1, picked.length) }) : t('plan.edit.switch.add')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
