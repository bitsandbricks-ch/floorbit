import { Button, Group, Paper } from '@mantine/core'
import { IconArrowLeft, IconPrinter } from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { CableList } from '@/api/types'
import { CableForm, type CableDraft } from '@/components/CableModal'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { EmptyState, ErrorBanner, LoadingState } from '@/components/ui'

const START: (keyof CableDraft)[] = ['switch', 'port', 'panel', 'panel_port', 'seat']

/** One cable on its own page (/cables/<id>, what its label's QR code opens), or a new one at
 *  /cables/new, which takes its switch, port and seat from the address (issue #877). */
export default function CablePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const id = useParams().id ?? ''
  const [params] = useSearchParams()
  const canEdit = useCan('floorplan.edit')
  const isNew = id === 'new'
  const query = useQuery({ queryKey: qk.cables, queryFn: () => get<CableList>('/api/cables') })
  const refresh = () => qc.invalidateQueries({ queryKey: qk.cables })
  useLiveEvent('cables.changed', () => void refresh())
  const cable = query.data?.cables.find((c) => c.id === id) ?? null
  const initial = Object.fromEntries(START.map((k) => [k, params.get(k) ?? '']).filter(([, v]) => v))
  const title = isNew ? t('cables.add') : cable?.label || t('cables.title')
  const kicker = cable ? [`${cable.switch} ${cable.port}`, cable.panel ? `${cable.panel} ${cable.panel_port}`.trim() : '', cable.seat]
    .filter(Boolean).join(' → ') : undefined
  const back = <Button component={Link} to="/cables" variant="default" leftSection={<IconArrowLeft size={16} />}>{t('cables.back')}</Button>

  return (
    <Layout title={title} back={{ href: '/cables', label: t('cables.title') }}>
      <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
      {query.isPending ? <LoadingState rows={6} /> : isNew && !canEdit ? (
        <EmptyState title={t('cables.noRights')} action={back} />
      ) : !isNew && !cable ? (
        <EmptyState title={t('cables.notFound')} action={back} />
      ) : (
        <>
          <PageHead title={title} eyebrow={kicker}
            actions={cable && (
              <Group gap="xs">
                <Button variant="default" component="a" target="_blank" leftSection={<IconPrinter size={16} />}
                  href={`/api/cables/labels.pdf?ids=${cable.id}`}>{t('cables.printOne')}</Button>
              </Group>
            )} />
          <Paper withBorder p="md" maw={880}>
            <CableForm key={cable ? `${cable.id}-${cable.updated_at}` : 'new'} cable={cable} canEdit={canEdit} initial={initial} print={false}
              onDone={({ saved, removed }) => {
                void refresh()
                if (removed) navigate('/cables')
                else if (saved && isNew) navigate(`/cables/${saved.id}`, { replace: true })
              }} />
          </Paper>
        </>
      )}
    </Layout>
  )
}
