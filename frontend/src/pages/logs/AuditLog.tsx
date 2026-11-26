import { Badge, Box, Button, Group, Paper, Select, Stack, Text, TextInput } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { useInfiniteQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { AuditEntry, AuditPage } from '@/api/types'
import { DataTable, ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { fieldsText } from '@/lib/auditFields'
import { dateTime } from '@/lib/time'

const PAGE = 100
// The address keys, apart from the Logs page's own (q, device, seat, ...): API name -> address name.
const KEYS = { area: 'area', user: 'account', q: 'find' } as const

/** Logs > Audit log (#1643): every change and sign-in, newest first, page by page, with its own
 *  filters and the CSV. The filters live in the link, so a filtered view can be shared or reloaded. */
export function AuditLog() {
  const { t, i18n } = useTranslation()
  const areaText = (a: string) => t(`audit.areas.${a}`, { defaultValue: a })
  const [params, setParams] = useSearchParams()
  const [area, setArea] = useState(params.get(KEYS.area) ?? '')
  const [user, setUser] = useState(params.get(KEYS.user) ?? '')
  const [q, setQ] = useState(params.get(KEYS.q) ?? '')
  const [typed] = useDebouncedValue({ user: user.trim(), q: q.trim() }, 250)
  const filters = new URLSearchParams()
  for (const [k, v] of [['area', area], ['user', typed.user], ['q', typed.q]]) if (v) filters.set(k, v)
  const shown = filters.toString()

  useEffect(() => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      for (const k of Object.values(KEYS)) next.delete(k)
      for (const [k, v] of new URLSearchParams(shown)) next.set(KEYS[k as keyof typeof KEYS], v)
      return next.toString() === prev.toString() ? prev : next
    }, { replace: true })
  }, [shown, setParams])

  const query = useInfiniteQuery({
    queryKey: [...qk.audit, shown],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => {
      const p = new URLSearchParams(shown)
      p.set('limit', String(PAGE))
      p.set('offset', String(pageParam))
      return get<AuditPage>(`/api/settings/audit?${p}`)
    },
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((n, page) => n + page.entries.length, 0)
      return loaded < last.total ? loaded : undefined
    },
  })
  const rows: AuditEntry[] = query.data?.pages.flatMap((p) => p.entries) ?? []
  const total = query.data?.pages[0]?.total ?? 0
  const areas = query.data?.pages[0]?.areas ?? []
  const when = (iso: string) => {
    const d = new Date(iso)
    return Number.isNaN(d.getTime()) ? iso : dateTime(d, i18n.language, true)
  }

  return (
      <Paper withBorder radius="lg" p="md">
        <Stack gap="sm">
          <Group align="flex-end" gap="sm" role="search">
            <Select label={t('audit.area')} w={{ base: '100%', sm: 170 }} value={area} onChange={(v) => setArea(v ?? '')} allowDeselect={false}
              data={[{ value: '', label: t('audit.allAreas') }, ...areas.map((a) => ({ value: a, label: areaText(a) }))]} />
            <TextInput label={t('audit.account')} placeholder={t('audit.any')} w={{ base: '100%', sm: 170 }} value={user} autoCapitalize="none"
              spellCheck={false} onChange={(e) => setUser(e.currentTarget.value)} />
            <TextInput label={t('audit.search')} placeholder={t('audit.searchHint')} style={{ flex: 1, minWidth: 180 }}
              type="search" value={q} onChange={(e) => setQ(e.currentTarget.value)} />
            <Button component="a" variant="default" href={`/api/settings/audit.csv${shown ? `?${shown}` : ''}`}>
              {t('audit.csv')}
            </Button>
          </Group>
          <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
          {query.isPending && <LoadingState rows={2} />}
          <Text size="sm" c="dimmed" role="status" aria-live="polite">
            {total ? t('audit.showing', { shown: rows.length, total }) : ''}
          </Text>
          {/* Phones: one block per entry instead of a table five columns wide. */}
          <Stack gap={0} hiddenFrom="sm">
            {query.isSuccess && !total && <Text c="dimmed" size="sm">{t('audit.empty')}</Text>}
            {rows.map((e, i) => (
              <Stack key={`${e.time}-${i}`} gap={2} py="xs" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }}>
                <Group gap="xs" wrap="nowrap" justify="space-between">
                  <Text size="sm" fw={600} c={e.ok === false ? 'down' : undefined}>
                    {e.action}{e.ok === false ? ` · ${t('audit.failed')}` : ''}
                  </Text>
                  <Badge variant="light" color="gray" style={{ flexShrink: 0 }}>{areaText(e.area)}</Badge>
                </Group>
                {e.target && <Text size="sm" style={{ overflowWrap: 'anywhere' }}>{e.target}</Text>}
                {e.reason && <Text size="sm" style={{ overflowWrap: 'anywhere' }}>{t('audit.reason', { reason: e.reason })}</Text>}
                <Text size="xs" c="dimmed">
                  {when(e.time)} · {e.user || t('audit.nobody')}
                  {e.fields?.length ? ` · ${fieldsText(t, e.area, e.fields)}` : ''}
                </Text>
              </Stack>
            ))}
          </Stack>
          <Box visibleFrom="sm">
            {/* Newest first, page by page from the server: the order is the log's, so no column sorts. */}
            <DataTable fill label={t('audit.title')} rows={rows} rowKey={(e, i) => `${e.time}-${i}`} pageSize={0} bare striped minWidth={640}
              empty={query.isSuccess && !total ? <Text c="dimmed" size="sm">{t('audit.empty')}</Text> : null}
              columns={[
                { id: 'when', header: t('audit.when'), cell: (e) => <span title={e.time}>{when(e.time)}</span> },
                { id: 'account', header: t('audit.account'), cell: (e) => <Text span size="sm" c={e.user ? undefined : 'dimmed'}>{e.user || t('audit.nobody')}</Text> },
                { id: 'area', header: t('audit.area'), cell: (e) => <Badge variant="light" color="gray" tt="none" miw="max-content">{areaText(e.area)}</Badge> },
                { id: 'what', header: t('audit.what'), wrap: true, cell: (e) => (
                  <>
                    <Text size="sm" c={e.ok === false ? 'down' : undefined}>{e.action}{e.ok === false ? ` · ${t('audit.failed')}` : ''}</Text>
                    {e.target && <Text size="xs" c="dimmed">{e.target}</Text>}
                    {e.reason && <Text size="xs">{t('audit.reason', { reason: e.reason })}</Text>}
                  </>
                ) },
                // Only while some entry names fields: an empty column says nothing (#1433).
                ...(rows.some((e) => e.fields?.length) ? [{ id: 'fields', header: t('audit.fields'), wrap: true, cell: (e: AuditEntry) => <Text size="xs" c="dimmed">{fieldsText(t, e.area, e.fields)}</Text> }] : []),
              ]} />
          </Box>
          {query.hasNextPage && (
            <Group justify="center">
              <Button variant="default" loading={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
                {t('audit.older')}
              </Button>
            </Group>
          )}
        </Stack>
      </Paper>
  )
}
