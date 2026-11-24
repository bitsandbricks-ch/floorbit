import { Anchor, Badge, Group, Stack, Switch, Text } from '@mantine/core'
import { IconCircleCheck, IconCircleDashed, IconInfoCircle } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { get, put } from '@/api/client'
import { qk } from '@/api/keys'
import { Panel } from '@/components/ui'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'

type Need = { id: string; ok: boolean | null; href: string | null }
type Part = { kind: 'setting' | 'feature' | 'plugin'; id: string; on: boolean }
export type Capability = { id: string; state: 'on' | 'off' | 'partly'; forced_off: boolean; parts: Part[]; needs: Need[] }

const key = [...qk.featureSettings, 'capabilities']
const STATE_COLOR = { on: 'up', partly: 'warn', off: 'gray' }

/** What a capability still needs: done, missing (with where to do it), or outside Floorbit. */
function NeedLine({ need }: { need: Need }) {
  const { t } = useTranslation()
  const label = t(`features.cap.need.${need.id}`, { defaultValue: need.id })
  const Icon = need.ok === null ? IconInfoCircle : need.ok ? IconCircleCheck : IconCircleDashed
  const color = need.ok === null ? 'var(--mantine-color-dimmed)' : need.ok ? 'var(--mantine-color-up-filled)' : 'var(--mantine-color-warn-filled)'
  const text = <Text size="sm" c={need.ok ? 'dimmed' : undefined}>{label}</Text>
  return (
    <Group gap={8} wrap="nowrap" align="flex-start" data-need={need.id} data-ok={String(need.ok)}>
      <Icon size={16} color={color} aria-hidden style={{ flex: 'none', marginTop: 3 }} />
      <div>
        {need.href && !need.ok
          ? (need.href.startsWith('#') ? <Anchor href={need.href} size="sm">{label}</Anchor>
            : <Anchor component={Link} to={need.href} size="sm">{label}</Anchor>)
          : text}
        {need.ok === null && <Text size="xs" c="dimmed">{t('features.cap.outside')}</Text>}
      </div>
    </Group>
  )
}

/** One switch per capability (#989): it turns its settings, features and plugins on together, then
 *  lists what it still needs. */
export function Capabilities({ onChanged }: { onChanged: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: key, queryFn: () => get<{ capabilities: Capability[] }>('/api/settings/capabilities') })
  const change = useMutation({
    mutationFn: ({ id, on }: { id: string; on: boolean }) => put<{ capabilities: Capability[] }>(`/api/settings/capabilities/${id}`, { on }),
    onSuccess: (answer) => { qc.setQueryData(key, answer); onChanged() },
  })
  if (q.isPending) return <LoadingState rows={3} />
  if (!q.data) return <ErrorBanner error={q.error} />
  const name = (id: string) => t(`features.cap.name.${id}`)
  return (
    <Panel title={t('features.cap.title')} desc={t('features.cap.intro')}>
      <ErrorBanner error={change.error} />
      <Stack gap={0} className="fb-setting-rows">
        {q.data.capabilities.map((c) => {
          const missing = c.needs.filter((n) => n.ok !== true)
          const offParts = c.parts.filter((p) => !p.on)
          return (
            <div key={c.id} id={`cap-${c.id}`} className="fb-setting-row" data-cap={c.id}>
              <div className="fb-setting-about">
                <Group gap="xs">
                  <Text size="sm" fw={600} component="label" htmlFor={`cap-switch-${c.id}`}>{name(c.id)}</Text>
                  <Badge size="xs" variant="light" color={STATE_COLOR[c.state]} tt="none">{t(`features.cap.state.${c.state}`)}</Badge>
                </Group>
                <Text size="xs" c="dimmed">{t(`features.cap.desc.${c.id}`)}</Text>
                {c.state === 'partly' && (
                  <Text size="xs" c="warn">
                    {t('features.cap.partly', { parts: offParts.map((p) => t(`features.cap.part.${p.id}`, { defaultValue: p.id })).join(', ') })}
                  </Text>
                )}
                {c.forced_off && <Text size="xs" c="warn">{t('features.cap.forced')}</Text>}
                {c.state !== 'off' && missing.length > 0 && (
                  <Stack gap={4} mt={6} aria-label={t('features.cap.stillNeeds', { name: name(c.id) })}>
                    <Text size="xs" fw={600}>{t('features.cap.needsTitle')}</Text>
                    {c.needs.map((n) => <NeedLine key={n.id} need={n} />)}
                  </Stack>
                )}
              </div>
              <div className="fb-setting-control" style={{ justifyContent: 'flex-end' }}>
                <Switch id={`cap-switch-${c.id}`} size="md" checked={c.state === 'on'} disabled={c.forced_off || change.isPending}
                  onChange={(e) => change.mutate({ id: c.id, on: e.currentTarget.checked })} />
              </div>
            </div>
          )
        })}
      </Stack>
    </Panel>
  )
}
