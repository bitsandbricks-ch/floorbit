import { Badge, Button, Group, Stack, Text } from '@mantine/core'
import { IconAlertTriangle, IconCircleCheck, IconCircleDashed, IconPlayerSkipForward } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import { Panel } from '@/components/ui'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { useChecklist, type ChecklistStep } from './checklist'

const ICON = { done: IconCircleCheck, look: IconAlertTriangle, todo: IconCircleDashed, skipped: IconPlayerSkipForward }
const COLOR = { done: 'up', look: 'warn', todo: 'gray', skipped: 'gray' }

/** What the step has, or what it still misses, in one sentence from its facts. */
function says(t: TFunction, s: ChecklistStep): string {
  const f = s.facts
  const k = (key: string, o: Record<string, unknown> = {}) => t(`setup.check.${s.id}.${key}`, o)
  switch (s.id) {
    case 'event': {
      if (s.state === 'done') return k(f.logo ? 'done' : 'doneNoLogo')
      const missing = (['name', 'dates', 'logo'] as const).filter((x) => !f[x]).map((x) => k(`part.${x}`))
      return k('missing', { list: missing.join(', ') })
    }
    case 'inventory':
      return s.state === 'done' ? k('done', { count: f.devices as number }) : k(f.netbox ? 'netboxEmpty' : 'none')
    case 'monitoring': {
      if (s.state === 'done') return k('done', { connected: f.connected, count: f.agents as number })
      const parts = [!f.agents ? k('noAgent') : !f.connected ? k('offline') : null, !f.source ? k('noSource') : null]
      return parts.filter(Boolean).join(' ')
    }
    case 'floor':
      if (s.state === 'done') return k('done', { count: f.blocks as number, placed: f.placed, devices: f.devices })
      return [!f.blocks ? k('noBlocks') : null, !f.placed ? k('noSwitches') : null].filter(Boolean).join(' ')
    case 'seats':
      return s.state === 'done' ? k('done', { count: f.mapped as number }) : k(f.checkin ? 'checkinOnly' : 'none')
    case 'alerts':
      return s.state === 'done' ? (f.discord ? k('discord') : k('webhooks', { count: f.webhooks as number })) : k('none')
    case 'crew':
      return s.state === 'done' ? k('done', { count: f.users as number, teams: f.teams }) : k('alone')
    default:
      return ''
  }
}

/** The event's setup as a checklist: each step's state from what is really there, linking to the one place it is set. */
export function SetupChecklist() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const q = useChecklist()
  const mark = useMutation({
    mutationFn: ({ id, state }: { id: string; state: 'skipped' | 'open' }) => post(`/api/setup/steps/${id}`, { state }),
    onSettled: () => void qc.invalidateQueries({ queryKey: qk.setup }),
  })
  if (q.isPending) return <LoadingState rows={4} />
  if (!q.data) return <ErrorBanner error={q.error} />
  const steps = q.data.steps
  const finished = steps.filter((s) => s.state === 'done' || s.state === 'skipped').length
  return (
    <Panel title={t('setup.check.title')} desc={t('setup.check.progress', { done: finished, count: steps.length })}>
      <Stack gap={0} className="fb-setting-rows">
        {steps.map((s, i) => {
          const Icon = ICON[s.state]
          return (
            <div key={s.id} className="fb-setting-row fb-check-row" data-step={s.id} data-state={s.state}>
              <div className="fb-setting-about"><Group gap="sm" wrap="nowrap" align="flex-start">
                <Icon size={22} color={`var(--mantine-color-${COLOR[s.state]}-filled)`} aria-hidden style={{ flex: 'none', marginTop: 1 }} />
                <div>
                  <Group gap="xs">
                    <Text size="sm" fw={600}>{`${i + 1}. ${t(`setup.check.${s.id}.title`)}`}</Text>
                    <Badge size="xs" variant="light" color={COLOR[s.state]} tt="none">{t(`setup.check.state.${s.state}`)}</Badge>
                  </Group>
                  <Text size="xs" c="dimmed">{says(t, s)}</Text>
                </div>
              </Group></div>
              <Group gap="xs" className="fb-setting-control" justify="flex-end">
                {(s.state === 'look' || s.state === 'todo') && (
                  <Button size="compact-sm" variant="subtle" color="gray" loading={mark.isPending && mark.variables?.id === s.id}
                    onClick={() => mark.mutate({ id: s.id, state: 'skipped' })}>{t('setup.check.skip')}</Button>
                )}
                {s.state === 'skipped' && (
                  <Button size="compact-sm" variant="subtle" color="gray" onClick={() => mark.mutate({ id: s.id, state: 'open' })}>
                    {t('setup.check.unskip')}
                  </Button>
                )}
                <Button size="compact-sm" variant={s.state === 'done' ? 'default' : 'filled'} component={Link} to={s.href}
                  aria-label={`${t(s.state === 'done' ? 'setup.check.open' : 'setup.check.go')}: ${t(`setup.check.${s.id}.title`)}`}>
                  {t(s.state === 'done' ? 'setup.check.open' : 'setup.check.go')}
                </Button>
              </Group>
            </div>
          )
        })}
      </Stack>
      <ErrorBanner error={mark.error} />
    </Panel>
  )
}
