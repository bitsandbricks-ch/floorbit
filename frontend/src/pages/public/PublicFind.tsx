import { Alert, Button, Group, Paper, Stack, Text, TextInput, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { ApiError, get } from '@/api/client'
import { qk } from '@/api/keys'
import type { PlanDrawing } from '@/api/types'
import { HallSketch } from '@/components/HallSketch'
import { PageOff } from '@/components/PublicFeedNotes'
import { PublicPage } from '@/components/PublicPage'

type Found = { seat: string; block: string; row: number; rows: number; col: number; hall: string }
export type FindAnswer = { nicks: boolean; found?: Found; drawing?: PlanDrawing }

const ask = (q: string) => get<FindAnswer>(`/api/seat-finder${q ? `?q=${encodeURIComponent(q)}` : ''}`)
const code = (e: unknown) => (e instanceof ApiError ? (e.data.code as string | undefined) ?? String(e.status) : 'error')

/** "Find your seat" for players' phones (issue #18, docs/kiosk.md): type the seat from the ticket
 *  (or the nick, where the event allows it) and see where it is in the hall. No account; the big
 *  screen's QR code leads here. ``?q=`` is in the address so a found seat can be shared. */
export default function PublicFind() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const query = (params.get('q') ?? '').trim()
  const [typed, setTyped] = useState(query)
  const info = useQuery({ queryKey: qk.publicFind(''), queryFn: () => ask(''), retry: false })
  const result = useQuery({ queryKey: qk.publicFind(query), queryFn: () => ask(query), enabled: !!query, retry: false, staleTime: 60_000 })
  const title = t('publicFind.title')
  const nicks = info.data?.nicks ?? result.data?.nicks ?? false
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const q = typed.trim()
    if (q) setParams({ q }, { replace: false })
  }
  if (code(info.error) === 'off' || code(result.error) === 'off') {
    return <PublicPage title={title}><PageOff title={title} text={t('publicFind.off')} /></PublicPage>
  }
  const found = result.data?.found
  const failed = result.error ? code(result.error) : null
  return (
    <PublicPage title={title} size={found ? 'page' : 'form'}>
      <Paper withBorder radius="lg" p="lg">
        <Stack gap="sm">
          <Title order={1} size="h3">{title}</Title>
          <Text c="dimmed">{nicks ? t('publicFind.introNick') : t('publicFind.intro')}</Text>
          <form onSubmit={submit} role="search">
            <Group gap="xs" wrap="nowrap" align="flex-end">
              <TextInput flex={1} size="md" label={nicks ? t('publicFind.labelNick') : t('publicFind.label')}
                value={typed} onChange={(e) => setTyped(e.currentTarget.value)} placeholder="D-17"
                autoComplete="off" autoCapitalize="characters" autoFocus={!query} required
                styles={{ input: { textTransform: nicks ? undefined : 'uppercase' } }} />
              <Button type="submit" size="md" loading={result.isFetching}>{t('publicFind.go')}</Button>
            </Group>
          </form>
          {failed === 'none' && <Alert color="down" role="alert">{t('publicFind.none', { query })}</Alert>}
          {failed === 'busy' && <Alert color="warn" role="alert">{t('publicFind.busy')}</Alert>}
          {failed && failed !== 'none' && failed !== 'busy' && <Alert color="down" role="alert">{t('publicPages.unreachable')}</Alert>}
          {found && result.data?.drawing && (
            <>
              <Title order={2} size="h2" mt="sm">{t('publicFind.found', { seat: found.seat })}</Title>
              {found.hall && <Text fw={700}>{found.hall}</Text>}
              <Text>{t('publicFind.where', { block: found.block, row: found.row, rows: found.rows, col: found.col })}</Text>
              <HallSketch drawing={result.data.drawing} label={t('publicFind.map', { seat: found.seat })}
                cellClass={(c) => (c.hit ? 'hit' : '')} ring={(c) => c.hit} />
            </>
          )}
        </Stack>
      </Paper>
    </PublicPage>
  )
}
