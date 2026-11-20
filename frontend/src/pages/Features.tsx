import { Badge, Group, Stack, Switch, Text } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { FeatureState } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { LoadingState, ErrorBanner, Panel } from '@/components/ui'
import { Capabilities } from './features/Capabilities'

type Answer = { features: FeatureState[]; env: string }

// Switched with their capability above (features/Capabilities.tsx), so not twice.
const IN_CAPABILITIES = new Set(['syslog', 'traffic', 'power'])

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
      <Stack gap="md">
        <Capabilities onChanged={() => {
          void qc.invalidateQueries({ queryKey: qk.featureSettings, exact: true })
          void qc.invalidateQueries({ queryKey: qk.features, exact: true })
        }} />
        <Panel title={t('features.others')} desc={t('features.othersIntro')}>
          <ErrorBanner error={error} />
          <Stack gap={0} className="fb-setting-rows">
            {query.isPending ? <LoadingState /> : d && d.features.filter((f) => !IN_CAPABILITIES.has(f.id)).map((f) => {
              const blockedBy = f.needs.filter((n) => !d.features.find((o) => o.id === n)?.on)
              return (
                <div key={f.id} className="fb-setting-row" data-feature={f.id}>
                  <div className="fb-setting-about">
                    <Group gap={6}>
                      <Text size="sm" fw={600}>{name(f.id)}</Text>
                      {f.on ? <Badge size="xs" variant="light" color="up" tt="none">{t('features.on')}</Badge>
                        : <Badge size="xs" variant="light" color="gray" tt="none">{t('features.off')}</Badge>}
                    </Group>
                    <Text size="xs" c="dimmed">{t(`features.desc.${f.id}`, { defaultValue: '' })}</Text>
                    {f.forced_off && <Text size="xs" c="warn">{t('features.forced', { env: d.env })}</Text>}
                    {!f.forced_off && f.chosen && blockedBy.length > 0 && (
                      <Text size="xs" c="warn">{t('features.needs', { names: blockedBy.map(name).join(', ') })}</Text>
                    )}
                  </div>
                  <div className="fb-setting-control" style={{ justifyContent: 'flex-end' }}>
                    <Switch size="md" aria-label={name(f.id)} checked={f.chosen && !f.forced_off} disabled={f.forced_off || change.isPending}
                      onChange={(e) => change.mutate({ [f.id]: e.currentTarget.checked })} />
                  </div>
                </div>
              )
            })}
          </Stack>
        </Panel>
      </Stack>
    </Layout>
  )
}
