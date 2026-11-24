import { Button, Paper, Stack, Text, Title } from '@mantine/core'
import { IconArrowLeft, IconPlus } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { del, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { usePower } from '@/api/queries'
import type { PowerBoard } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { EmptyState, ErrorBanner, LoadingState } from '@/components/ui'
import { BoardForm } from './Forms'
import { CircuitTable } from './parts'
import { boardPath } from './state'
import { ConfirmButton } from '@bitsandbricks/ui'

/** One distribution board (/power/boards/<id>, or /new): its details and its circuits (issue #877). */
export default function BoardPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const client = useQueryClient()
  const id = useParams().id ?? ''
  const isNew = id === 'new'
  const power = usePower()
  const refresh = () => client.invalidateQueries({ queryKey: qk.power })
  useLiveEvent('power.changed', () => void refresh())
  const data = power.data
  const board = data?.boards.find((b) => b.id === id) ?? null
  const circuits = data?.circuits.filter((c) => c.board === id) ?? []
  const save = useMutation({
    mutationFn: (body: Partial<PowerBoard>) => (isNew ? post<PowerBoard>('/api/power/boards', body) : patch<PowerBoard>(`/api/power/boards/${id}`, body)),
    onSuccess: async (saved) => { await refresh(); if (isNew && saved?.id) navigate(boardPath(saved.id), { replace: true }) },
  })
  const remove = useMutation({ mutationFn: () => del(`/api/power/boards/${id}`), onSuccess: async () => { await refresh(); navigate('/power') } })
  const back = { href: '/power', label: t('power.title') }
  const title = isNew ? t('power.newBoard') : board?.name ?? t('power.title')
  const backButton = <Button component={Link} to="/power" variant="default" leftSection={<IconArrowLeft size={16} />}>{t('power.back')}</Button>

  return (
    <Layout title={title} back={back}>
      <ErrorBanner error={power.error} mb="md" />
      {power.isPending || !data ? <LoadingState rows={6} /> : (isNew && !data.can_edit) || (!isNew && !board) ? (
        <EmptyState title={isNew ? t('power.noRights') : t('power.boardGone')} action={backButton} />
      ) : (
        <>
          <PageHead title={title} kicker={board?.location || undefined}
            actions={board && data.can_edit && (
              <Button leftSection={<IconPlus size={16} />} component={Link} to={`/power/circuits/new?board=${encodeURIComponent(board.id)}`}>
                {t('power.addCircuit')}
              </Button>
            )} />
          <Stack gap="md">
            {board && (
              <Paper withBorder p="md">
                <Title order={2} size="h5" mb="xs">{t('power.circuits')}</Title>
                {circuits.length ? <CircuitTable circuits={circuits} /> : <Text c="dimmed" size="sm">{t('power.noCircuits')}</Text>}
              </Paper>
            )}
            {data.can_edit ? (
              <Paper withBorder p="md" maw={720}>
                <Title order={2} size="h5" mb="xs">{t('power.details')}</Title>
                <BoardForm key={board ? JSON.stringify(board) : 'new'} board={board} busy={save.isPending}
                  error={save.error?.message ?? remove.error?.message ?? null} onSave={(body) => save.mutate(body)}
                  extra={board && !circuits.length ? (
                    <ConfirmButton variant="subtle" danger label={t('power.remove')}
                      question={t('power.removeBoardConfirm', { name: board.name })} onConfirm={() => remove.mutate()} />
                  ) : undefined} />
              </Paper>
            ) : null}
          </Stack>
        </>
      )}
    </Layout>
  )
}
