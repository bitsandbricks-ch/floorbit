import {
  Alert, Autocomplete, Badge, Button, Group, Loader, Modal, Paper, SegmentedControl, Select, Stack, Table, Text, TextInput, Title,
} from '@mantine/core'
import { IconArrowBackUp, IconPrinter, IconSearch } from '@tabler/icons-react'
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

type Show = 'all' | 'out' | 'in' | 'late'

function ItemModal({ item, people, onClose, onDone }: {
  item: GearItem; people: GearData['people']; onClose: () => void; onDone: () => void
}) {
  const { t } = useTranslation()
  const [to, setTo] = useState('')
  const [kind, setKind] = useState<'person' | 'area'>('person')
  const [note, setNote] = useState('')
  const [until, setUntil] = useState('')
  const act = useMutation({
    mutationFn: () => item.loan
      ? post(`/api/gear/${item.id}/in`, { note: note.trim() })
      : post(`/api/gear/${item.id}/out`, { to: to.trim(), kind, note: note.trim(),
        until: until ? new Date(until).getTime() / 1000 : null }),
    onSuccess: onDone,
  })
  return (
    <Modal opened onClose={onClose} title={item.name}>
      <Stack gap="sm">
        <Text size="sm" c="dimmed">{[t(`gear.role.${item.role}`, { defaultValue: item.role }), item.model, item.serial].filter(Boolean).join(' · ')}</Text>
        {item.loan ? (
          <Alert color={item.loan.overdue ? 'down' : 'warn'}>
            {t('gear.outWith', { to: item.loan.to, when: when(item.loan.at) })}{item.loan.note ? ` · ${item.loan.note}` : ''}
            {item.loan.until ? ` · ${t(item.loan.overdue ? 'gear.overdue' : 'gear.dueBy', { when: when(item.loan.until) })}` : ''}
          </Alert>
        ) : (
          <>
            <SegmentedControl value={kind} onChange={(v) => setKind(v as 'person' | 'area')}
              data={[{ value: 'person', label: t('gear.toPerson') }, { value: 'area', label: t('gear.toArea') }]} />
            {kind === 'person' ? (
              <Autocomplete label={t('gear.who')} value={to} onChange={setTo} data={people.map((p) => p.display_name)} limit={20} />
            ) : (
              <TextInput label={t('gear.where')} placeholder={t('gear.wherePlaceholder')} value={to} onChange={(e) => setTo(e.currentTarget.value)} />
            )}
            <TextInput type="datetime-local" label={t('gear.backBy')} value={until} onChange={(e) => setUntil(e.currentTarget.value)} />
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
// Teardown: a helper brings back a whole box at once (issue #320). One request per piece keeps the
// log and the live events the same as checking each in by hand.
function CheckInAll({ to, items, onClose, onDone }: {
  to: string; items: GearItem[]; onClose: () => void; onDone: () => void
}) {
  const { t } = useTranslation()
  const [note, setNote] = useState('')
  const act = useMutation({
    mutationFn: async () => {
      for (const i of items) await post(`/api/gear/${i.id}/in`, { note: note.trim() })
    },
    onSuccess: onDone,
  })
  return (
    <Modal opened onClose={onClose} title={t('gear.allBackTitle', { to })}>
      <Stack gap="sm">
        <Text size="sm">{items.map((i) => i.name).join(', ')}</Text>
        <TextInput label={t('gear.note')} value={note} onChange={(e) => setNote(e.currentTarget.value)} />
        {act.error && <Alert color="down" role="alert">{t('common.error', { message: act.error.message })}</Alert>}
        <Button fullWidth loading={act.isPending} onClick={() => act.mutate()}>
          {t('gear.allBackDo', { count: items.length })}
        </Button>
      </Stack>
    </Modal>
  )
}

export default function Gear() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.gear, queryFn: () => get<GearData>('/api/gear') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.gear })
  useLiveEvent('gear.changed', refresh)
  useLiveEvent('data.changed', refresh)
  // ?holder= comes from the teardown list (issue #322): open straight on that person's pieces.
  const [search, setSearch] = useState(() => new URLSearchParams(window.location.search).get('holder') ?? '')
  const [show, setShow] = useState<Show>(() => new URLSearchParams(window.location.search).get('holder') ? 'out' : 'all')
  const [role, setRole] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(() => new URLSearchParams(window.location.search).get('item'))
  const [allBack, setAllBack] = useState(false)
  const d = query.data
  const roles = d ? [...new Set(d.items.map((i) => i.role))] : []
  const q = search.trim().toLowerCase()
  const rows = (d?.items ?? []).filter((i) => (!role || i.role === role)
    && (show === 'all' || (show === 'late' ? !!i.loan?.overdue : (show === 'out') === !!i.loan))
    && (!q || [i.name, i.model, i.serial, i.loan?.to ?? ''].some((v) => v.toLowerCase().includes(q))))
  const current = d?.items.find((i) => i.id === open)
  const outCount = d?.items.filter((i) => i.loan).length ?? 0
  const lateCount = d?.items.filter((i) => i.loan?.overdue).length ?? 0
  // Who has how much, most first (issue #318): at teardown the question is "who still has our stuff".
  const holders = Object.entries((d?.items ?? []).reduce<Record<string, number>>((acc, i) => {
    if (i.loan) acc[i.loan.to] = (acc[i.loan.to] ?? 0) + 1
    return acc
  }, {})).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  const holder = holders.some(([to]) => to === search) ? search : null
  const held = holder ? (d?.items ?? []).filter((i) => i.loan?.to === holder) : []

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
                data={[{ value: 'all', label: t('gear.all') }, { value: 'out', label: t('gear.out', { count: outCount }) },
                  ...(lateCount || show === 'late' ? [{ value: 'late', label: t('gear.lateTab', { count: lateCount }) }] : []),
                  { value: 'in', label: t('gear.in') }]} />
            </Group>
            {holders.length > 0 && (
              <Group gap={6} role="group" aria-label={t('gear.holders')}>
                <Text size="sm" fw={600}>{t('gear.holders')}:</Text>
                {holders.map(([to, n]) => (
                  <Button key={to} size="compact-sm" variant={search === to ? 'filled' : 'light'} color="warn"
                    aria-pressed={search === to} onClick={() => { setSearch(search === to ? '' : to); setShow(search === to ? 'all' : 'out') }}>
                    {t('gear.holder', { to, count: n })}
                  </Button>
                ))}
                {holder && (
                  <Button size="compact-sm" variant="default" leftSection={<IconArrowBackUp size={14} />} onClick={() => setAllBack(true)}>
                    {t('gear.allBack', { count: held.length })}
                  </Button>
                )}
              </Group>
            )}
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
                              ? (
                                <Group gap={6}>
                                  <Badge variant="light" color="warn" tt="none">{t('gear.outWith', { to: i.loan.to, when: when(i.loan.at) })}</Badge>
                                  {i.loan.until && (i.loan.overdue
                                    ? <Badge variant="filled" color="down" tt="none">{t('gear.overdue', { when: when(i.loan.until) })}</Badge>
                                    : <Text span size="xs" c="dimmed">{t('gear.dueBy', { when: when(i.loan.until) })}</Text>)}
                                </Group>
                              )
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
      {allBack && holder && <CheckInAll to={holder} items={held} onClose={() => setAllBack(false)}
        onDone={() => { setAllBack(false); setSearch(''); setShow('all'); refresh() }} />}
    </Layout>
  )
}
