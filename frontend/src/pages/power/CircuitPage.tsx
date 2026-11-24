import { Anchor, Button, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { IconArrowLeft } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { del, get, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { usePower } from '@/api/queries'
import type { Circuit } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { EmptyState, ErrorBanner, LoadingState } from '@/components/ui'
import { CircuitForm, ReadingForm } from './Forms'
import { Feeds, Load, StateBadge } from './parts'
import { boardPath, circuitPath } from './state'
import { ConfirmButton } from '@bitsandbricks/ui'

/** One circuit (/power/circuits/<id>, or /new?board=): its load, a reading to type in, whether it
 *  tripped, what it feeds and its details (issue #877). */
export default function CircuitPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const client = useQueryClient()
  const id = useParams().id ?? ''
  const [params] = useSearchParams()
  const isNew = id === 'new'
  const power = usePower()
  const switches = useQuery({ queryKey: qk.switches, queryFn: () => get<{ id: string; name: string }[]>('/api/switches') })
  const refresh = () => client.invalidateQueries({ queryKey: qk.power })
  useLiveEvent('power.changed', () => void refresh())
  const data = power.data
  const circuit = data?.circuits.find((c) => c.id === id) ?? null
  const board = data?.boards.find((b) => b.id === circuit?.board)
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => (isNew ? post<Circuit>('/api/power/circuits', body) : patch<Circuit>(`/api/power/circuits/${id}`, body)),
    onSuccess: async (saved) => { await refresh(); if (isNew && saved?.id) navigate(circuitPath(saved.id), { replace: true }) },
  })
  const reading = useMutation({ mutationFn: (body: unknown) => post(`/api/power/circuits/${id}/reading`, body), onSuccess: refresh })
  const trip = useMutation({ mutationFn: (tripped: boolean) => post(`/api/power/circuits/${id}/trip`, { tripped }), onSuccess: refresh })
  const remove = useMutation({
    mutationFn: () => del(`/api/power/circuits/${id}`),
    onSuccess: async () => { await refresh(); navigate(board ? boardPath(board.id) : '/power') },
  })
  const title = isNew ? t('power.newCircuit') : circuit?.name ?? t('power.title')
  const backButton = <Button component={Link} to="/power" variant="default" leftSection={<IconArrowLeft size={16} />}>{t('power.back')}</Button>

  return (
    <Layout title={title} back={board ? { href: boardPath(board.id), label: board.name } : { href: '/power', label: t('power.title') }}>
      <ErrorBanner error={power.error ?? trip.error} mb="md" />
      {power.isPending || !data ? <LoadingState rows={6} /> : (isNew && (!data.can_edit || !data.boards.length)) || (!isNew && !circuit) ? (
        <EmptyState title={isNew ? t('power.noRights') : t('power.circuitGone')} action={backButton} />
      ) : (
        <>
          <PageHead title={title}
            eyebrow={circuit && board ? <><Anchor component={Link} to={boardPath(board.id)} inherit>{board.name}</Anchor> · {circuit.phase} · {circuit.rating_a} A</> : undefined}
            actions={circuit && data.can_read && (circuit.tripped
              ? <Button color="up" loading={trip.isPending} onClick={() => trip.mutate(false)}>{t('power.backOn')}</Button>
              : <Button color="down" variant="light" loading={trip.isPending} onClick={() => trip.mutate(true)}>{t('power.tripped')}</Button>)} />
          <Stack gap="md">
            {circuit && (
              <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
                <Paper withBorder p="md">
                  <Title order={2} size="h5" mb="xs">{t('power.load')} <StateBadge c={circuit} /></Title>
                  <Load c={circuit} />
                  {data.can_read && (
                    <Stack mt="md" gap="xs">
                      <Text size="sm" fw={600}>{t('power.readingTitle', { name: circuit.name })}</Text>
                      <ReadingForm key={circuit.reading?.at ?? 'none'} busy={reading.isPending} error={reading.error?.message ?? null}
                        onSave={(body) => reading.mutate(body)} />
                    </Stack>
                  )}
                </Paper>
                <Paper withBorder p="md">
                  <Title order={2} size="h5" mb="xs">{t('power.feeds')}</Title>
                  <Feeds c={circuit} />
                  {circuit.fed.seats.length > 0 && <Text size="xs" c="dimmed" mt={4}>{circuit.fed.seats.join(', ')}</Text>}
                </Paper>
              </SimpleGrid>
            )}
            {data.can_edit && (
              <Paper withBorder p="md" maw={880}>
                <Title order={2} size="h5" mb="xs">{t('power.details')}</Title>
                <CircuitForm key={circuit ? JSON.stringify([circuit.name, circuit.board, circuit.phase, circuit.rating_a, circuit.meter, circuit.blocks, circuit.switches]) : 'new'}
                  circuit={circuit} overview={data} switches={switches.data ?? []} startBoard={params.get('board')}
                  busy={save.isPending} error={save.error?.message ?? remove.error?.message ?? null} onSave={(body) => save.mutate(body)}
                  extra={circuit ? (
                    <ConfirmButton variant="subtle" danger label={t('power.remove')}
                      question={t('power.removeCircuitConfirm', { name: circuit.name })} onConfirm={() => remove.mutate()} />
                  ) : undefined} />
              </Paper>
            )}
          </Stack>
        </>
      )}
    </Layout>
  )
}
