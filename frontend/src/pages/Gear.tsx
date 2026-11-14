import {
  Alert, Autocomplete, Badge, Button, Group, Loader, Modal, Paper, SegmentedControl, Select, Stack, Table, Text, TextInput, Title,
} from '@mantine/core'
import { IconPrinter, IconSearch } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { GearData, GearItem } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { when } from './handover/format'

type Show = 'all' | 'out' | 'in'

function ItemModal({ item, people, onClose, onDone }: {
  item: GearItem; people: GearData['people']; onClose: () => void; onDone: () => void
}) {
  const { t } = useTranslation()
  const [to, setTo] = useState('')
  const [kind, setKind] = useState<'person' | 'area'>('person')
  const [note, setNote] = useState('')
  const act = useMutation({
    mutationFn: () => item.loan
      ? post(`/api/gear/${item.id}/in`, { note: note.trim() })
      : post(`/api/gear/${item.id}/out`, { to: to.trim(), kind, note: note.trim() }),
    onSuccess: onDone,
  })
  return (
    <Modal opened onClose={onClose} title={item.name}>
      <Stack gap="sm">
        <Text size="sm" c="dimmed">{[t(`gear.role.${item.role}`, { defaultValue: item.role }), item.model, item.serial].filter(Boolean).join(' · ')}</Text>
        {item.loan ? (
          <Alert color="warn">{t('gear.outWith', { to: item.loan.to, when: when(item.loan.at) })}{item.loan.note ? ` · ${item.loan.note}` : ''}</Alert>
        ) : (
          <>
            <SegmentedControl value={kind} onChange={(v) => setKind(v as 'person' | 'area')}
              data={[{ value: 'person', label: t('gear.toPerson') }, { value: 'area', label: t('gear.toArea') }]} />
            {kind === 'person' ? (
              <Autocomplete label={t('gear.who')} value={to} onChange={setTo} data={people.map((p) => p.display_name)} limit={20} />
            ) : (
              <TextInput label={t('gear.where')} placeholder={t('gear.wherePlaceholder')} value={to} onChange={(e) => setTo(e.currentTarget.value)} />
            )}
          </>
        )}
        <TextInput label={t('gear.note')} value={note} maxLength={300} onChange={(e) => setNote(e.currentTarget.value)} />
        {act.error && <Alert color="down" role="alert">{act.error.message}</Alert>}
        <Button size="md" fullWidth loading={act.isPending} disabled={!item.loan && !to.trim()} onClick={() => act.mutate()}
          color={item.loan ? 'up' : undefined}>
          {item.loan ? t('gear.checkIn') : t('gear.checkOut')}
        </Button>
      </Stack>
    </Modal>
  )
}

/** Who has which piece of gear. The gear itself comes from the inventory (NetBox). */
export default function Gear() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.gear, queryFn: () => get<GearData>('/api/gear') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.gear })
  useLiveEvent('gear.changed', refresh)
  useLiveEvent('data.changed', refresh)
  const [search, setSearch] = useState('')
  const [show, setShow] = useState<Show>('all')
  const [role, setRole] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(() => new URLSearchParams(window.location.search).get('item'))
  const d = query.data
  const roles = d ? [...new Set(d.items.map((i) => i.role))] : []
  const q = search.trim().toLowerCase()
  const rows = (d?.items ?? []).filter((i) => (!role || i.role === role)
    && (show === 'all' || (show === 'out') === !!i.loan)
    && (!q || [i.name, i.model, i.serial, i.loan?.to ?? ''].some((v) => v.toLowerCase().includes(q))))
  const current = d?.items.find((i) => i.id === open)
  const outCount = d?.items.filter((i) => i.loan).length ?? 0

  return (
    <Layout title={t('gear.title')} back={{ href: '/incidents', label: t('incidents.title') }}>
      <PageHead title={t('gear.title')} desc={t('gear.intro')}
        actions={
          <Button variant="default" component="a" target="_blank" leftSection={<IconPrinter size={16} />}
            href={`/api/gear/labels.pdf${role ? `?role=${encodeURIComponent(role)}` : ''}`}>
            {t('gear.labels')}
          </Button>
        } />
      <Stack gap="md">
        {query.error && <Alert color="down" role="alert">{t('common.error', { message: query.error.message })}</Alert>}
        {query.isPending ? <Loader aria-label={t('common.loading')} /> : d && (
          <>
            <Group gap="sm" wrap="wrap">
              <TextInput leftSection={<IconSearch size={14} />} aria-label={t('gear.search')} placeholder={t('gear.search')}
                value={search} onChange={(e) => setSearch(e.currentTarget.value)} style={{ flex: 1, minWidth: 200 }} />
              <Select aria-label={t('gear.kind')} placeholder={t('gear.allKinds')} clearable value={role} onChange={setRole} w={180}
                data={roles.map((r) => ({ value: r, label: t(`gear.role.${r}`, { defaultValue: r }) }))} />
              <SegmentedControl value={show} onChange={(v) => setShow(v as Show)}
                data={[{ value: 'all', label: t('gear.all') }, { value: 'out', label: t('gear.out', { count: outCount }) }, { value: 'in', label: t('gear.in') }]} />
            </Group>
            <Paper withBorder radius="lg" p="md">
              {rows.length === 0 ? <Text c="dimmed">{d.items.length ? t('gear.noMatch') : t('gear.empty')}</Text> : (
                <Table.ScrollContainer minWidth={560}>
                  <Table striped highlightOnHover>
                    <Table.Thead>
                      <Table.Tr><Table.Th>{t('gear.name')}</Table.Th><Table.Th>{t('gear.kind')}</Table.Th><Table.Th>{t('gear.status')}</Table.Th><Table.Th /></Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {rows.map((i) => (
                        <Table.Tr key={i.id}>
                          <Table.Td fw={600}>{i.name}</Table.Td>
                          <Table.Td>{[t(`gear.role.${i.role}`, { defaultValue: i.role }), i.model].filter(Boolean).join(' · ')}</Table.Td>
                          <Table.Td>
                            {i.loan
                              ? <Badge variant="light" color="warn" tt="none">{t('gear.outWith', { to: i.loan.to, when: when(i.loan.at) })}</Badge>
                              : <Badge variant="light" color="up" tt="none">{t('gear.here')}</Badge>}
                          </Table.Td>
                          <Table.Td>
                            <Button size="compact-sm" variant="default" onClick={() => setOpen(i.id)}>
                              {i.loan ? t('gear.checkIn') : t('gear.checkOut')}
                            </Button>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              )}
            </Paper>
            {d.log.length > 0 && (
              <Paper withBorder radius="lg" p="md">
                <Title order={2} size="h4" mb="xs">{t('gear.history')}</Title>
                <Stack gap={4}>
                  {d.log.slice(0, 15).map((e, n) => (
                    <Text key={n} size="sm">
                      <Text span c="dimmed">{when(e.at)}</Text>{' '}
                      {t(e.action === 'out' ? 'gear.logOut' : 'gear.logIn', { name: e.name, to: e.to, by: e.by ?? '?' })}
                    </Text>
                  ))}
                </Stack>
              </Paper>
            )}
          </>
        )}
      </Stack>
      {current && d && <ItemModal key={current.id + String(!!current.loan)} item={current} people={d.people}
        onClose={() => setOpen(null)} onDone={() => { setOpen(null); refresh() }} />}
    </Layout>
  )
}
