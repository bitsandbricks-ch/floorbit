import { Alert, Badge, Group, Loader, Paper, Stack, Switch, Text } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { FeatureState } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

type Answer = { features: FeatureState[]; env: string }

/** Turn whole features on or off. Off means gone: no link, no page, no API, no background work. */
export default function Features() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.featureSettings, queryFn: () => get<Answer>('/api/settings/features') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.features })
  useLiveEvent('features.changed', refresh)
  const change = useMutation({
    mutationFn: (body: Record<string, boolean>) => put<Answer>('/api/settings/features', body),
    onSuccess: (answer) => {
      qc.setQueryData(qk.featureSettings, answer)
      void qc.invalidateQueries({ queryKey: qk.features, exact: true })   // the links elsewhere
    },
  })
  const d = query.data
  const name = (id: string) => t(`features.name.${id}`, { defaultValue: id })
  const error = query.error ?? change.error

  return (
    <Layout title={t('features.title')} back={{ href: '/settings', label: t('features.settings') }}>
      <PageHead title={t('features.title')} desc={t('features.intro')} />
      <Stack gap="sm">
        {error && <Alert color="down" role="alert">{t('common.error', { message: error.message })}</Alert>}
        {query.isPending ? <Loader aria-label={t('common.loading')} /> : d && d.features.map((f) => {
          const blockedBy = f.needs.filter((n) => !d.features.find((o) => o.id === n)?.on)
          return (
            <Paper key={f.id} withBorder radius="lg" p="md">
              <Group justify="space-between" wrap="nowrap" align="flex-start">
                <Stack gap={2} style={{ minWidth: 0 }}>
                  <Group gap={6}>
                    <Text fw={600}>{name(f.id)}</Text>
                    {f.on ? <Badge variant="light" color="up" tt="none">{t('features.on')}</Badge>
                      : <Badge variant="light" color="trace" tt="none">{t('features.off')}</Badge>}
                  </Group>
                  <Text size="sm" c="dimmed">{t(`features.desc.${f.id}`, { defaultValue: '' })}</Text>
                  {f.forced_off && <Text size="xs" c="warn">{t('features.forced', { env: d.env })}</Text>}
                  {!f.forced_off && f.chosen && blockedBy.length > 0 && (
                    <Text size="xs" c="warn">{t('features.needs', { names: blockedBy.map(name).join(', ') })}</Text>
                  )}
                </Stack>
                <Switch size="md" aria-label={name(f.id)} checked={f.chosen && !f.forced_off} disabled={f.forced_off || change.isPending}
                  onChange={(e) => change.mutate({ [f.id]: e.currentTarget.checked })} />
              </Group>
            </Paper>
          )
        })}
      </Stack>
    </Layout>
  )
}
