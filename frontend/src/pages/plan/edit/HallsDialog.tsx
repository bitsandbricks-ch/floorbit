import { Anchor, Badge, Button, FileButton, Group, Modal, Paper, Stack, Text, TextInput } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconPhoto, IconPlus, IconTableImport, IconTrash } from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import type { Hall } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'

const IMAGES = 'image/png,image/jpeg,image/webp,image/svg+xml'

const read = (file: File, text: boolean) => new Promise<string>((resolve, reject) => {
  const r = new FileReader()
  r.onload = () => resolve(String(r.result))
  r.onerror = () => reject(r.error)
  if (text) r.readAsText(file); else r.readAsDataURL(file)
})

/** The halls of the event, as the older editor's Halls dialog: add, rename, open, delete an empty
 *  one, set or remove its background image, and import seat blocks from a CSV file. */
export function HallsDialog({ opened, current, onClose, onOpen, onChanged }: {
  opened: boolean; current: string; onClose: () => void; onOpen: (id: string) => void; onChanged: () => Promise<unknown>
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const halls = useQuery({ queryKey: qk.halls, queryFn: () => get<{ halls: Hall[] }>('/api/halls').then((d) => d.halls), enabled: opened })
  const [name, setName] = useState('')
  const [names, setNames] = useState<Record<string, string>>({})
  const done = async () => { await Promise.all([halls.refetch(), onChanged(), qc.invalidateQueries({ queryKey: qk.seatBlocks })]) }
  const fail = (err: unknown) => notifications.show({ color: 'down', title: t('plan.edit.failed'), message: err instanceof Error ? err.message : String(err) })
  const run = async (job: () => Promise<unknown>, ok?: string) => {
    try {
      await job()
      if (ok) notifications.show({ color: 'up', message: ok })
      await done()
    } catch (err) {
      fail(err)
    }
  }
  const add = async () => {
    if (!name.trim()) return
    await run(async () => { await post<Hall>('/api/halls', { name: name.trim() }); setName('') }, t('plan.edit.halls.added', { name: name.trim() }))
  }
  const rename = (h: Hall) => {
    const next = (names[h.id] ?? h.name).trim()
    if (next && next !== h.name) void run(() => put(`/api/halls/${encodeURIComponent(h.id)}`, { name: next }))
  }
  const background = (h: Hall, file: File | null) => {
    if (file) void run(async () => put(`/api/halls/${encodeURIComponent(h.id)}/background`, { image: await read(file, false) }), t('plan.edit.halls.backgroundSet'))
  }
  const csv = async (h: Hall, file: File | null) => {
    if (!file) return
    try {
      const res = await post<{ added: number }>(`/api/halls/${encodeURIComponent(h.id)}/seat-blocks.csv`, { csv: await read(file, true) })
      notifications.show({ color: 'up', message: t('plan.edit.halls.imported', { count: res.added }) })
      await done()
    } catch (err) {
      // The server says what's wrong, line by line: show the first few.
      const lines = err instanceof ApiError && Array.isArray(err.data.errors)
        ? (err.data.errors as { line?: number; error: string }[]).slice(0, 5).map((x) => (x.line ? `${t('plan.edit.halls.line', { line: x.line })}: ` : '') + x.error).join(' · ')
        : ''
      notifications.show({ color: 'down', title: t('plan.edit.halls.notImported'), message: lines || (err instanceof Error ? err.message : String(err)), autoClose: 12_000 })
    }
  }
  const remove = async (h: Hall) => {
    await run(async () => {
      await del(`/api/halls/${encodeURIComponent(h.id)}`)
      if (h.id === current) onOpen((halls.data ?? []).find((x) => x.id !== h.id)!.id)
    })
  }
  const list = halls.data ?? []
  return (
    <Modal opened={opened} onClose={onClose} title={t('plan.edit.halls.title')} size="lg">
      <Stack gap="sm">
        {list.map((h) => (
          <Paper key={h.id} withBorder p="sm" radius="md">
            <Stack gap="xs">
              <Group gap="xs" wrap="nowrap" align="flex-end">
                <TextInput style={{ flex: 1 }} label={t('plan.edit.halls.name')} maxLength={60} value={names[h.id] ?? h.name}
                  onChange={(e) => { const v = e.currentTarget.value; setNames((n) => ({ ...n, [h.id]: v })) }}
                  onBlur={() => rename(h)} onKeyDown={(e) => { if (e.key === 'Enter') rename(h) }} />
                {h.id === current
                  ? <Badge variant="light" mb={8}>{t('plan.edit.halls.shown')}</Badge>
                  : <Button variant="default" onClick={() => { onOpen(h.id); onClose() }}>{t('plan.edit.halls.open')}</Button>}
              </Group>
              <Text size="xs" c="dimmed">{t('plan.edit.halls.counts', { switches: h.switches, blocks: h.seat_blocks })}{h.background ? ` · ${t('plan.edit.halls.hasBackground')}` : ''}</Text>
              <Group gap="xs">
                <FileButton accept={IMAGES} onChange={(f) => background(h, f)}>
                  {(p) => <Button {...p} size="xs" variant="default" leftSection={<IconPhoto size={14} />}>{t(h.background ? 'plan.edit.halls.replaceBackground' : 'plan.edit.halls.background')}</Button>}
                </FileButton>
                {h.background && (
                  <Button size="xs" variant="subtle" color="gray" onClick={() => void run(() => del(`/api/halls/${encodeURIComponent(h.id)}/background`))}>
                    {t('plan.edit.halls.removeBackground')}
                  </Button>
                )}
                <FileButton accept=".csv,text/csv" onChange={(f) => void csv(h, f)}>
                  {(p) => <Button {...p} size="xs" variant="default" leftSection={<IconTableImport size={14} />}>{t('plan.edit.halls.csv')}</Button>}
                </FileButton>
                {list.length > 1 && (
                  <ConfirmButton size="xs" variant="subtle" danger leftSection={<IconTrash size={14} />} label={t('plan.edit.halls.delete')}
                    question={t('plan.edit.halls.deleteText', { name: h.name })} onConfirm={() => void remove(h)} />
                )}
              </Group>
            </Stack>
          </Paper>
        ))}
        <form onSubmit={(e) => { e.preventDefault(); void add() }}>
          <Group gap="xs" wrap="nowrap" align="flex-end">
            <TextInput style={{ flex: 1 }} label={t('plan.edit.halls.new')} placeholder={t('plan.edit.halls.newHint')} maxLength={60} value={name}
              onChange={(e) => setName(e.currentTarget.value)} />
            <Button type="submit" leftSection={<IconPlus size={14} />} disabled={!name.trim()}>{t('plan.edit.halls.add')}</Button>
          </Group>
        </form>
        <Text size="xs" c="dimmed">{t('plan.edit.halls.csvHelp')} <Anchor href="/templates" size="xs">{t('plan.edit.halls.templates')}</Anchor></Text>
      </Stack>
    </Modal>
  )
}
