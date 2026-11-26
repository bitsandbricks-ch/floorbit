import { Anchor, Badge, Button, Group, SimpleGrid, Stack, Switch, Text, ThemeIcon, Title } from '@mantine/core'
import { IconCircleCheck, IconCircleDashed, IconInfoCircle, type Icon } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createElement } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { get, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { FeatureState } from '@/api/types'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { pageIcon } from '@/nav/sections'
import { PluginCard } from './Card'

type Need = { id: string; ok: boolean | null; href: string | null }
type Part = { kind: 'setting' | 'feature' | 'plugin'; id: string; on: boolean }
export type Capability = { id: string; state: 'on' | 'off' | 'partly'; forced_off: boolean; parts: Part[]; needs: Need[] }
type Features = { features: FeatureState[]; env: string }

const capKey = [...qk.featureSettings, 'capabilities']
const STATE_COLOR = { on: 'up', partly: 'warn', off: 'gray' } as const
// The page each one opens, for its icon, where the ids differ.
const PAGE: Record<string, string> = { front_door: 'checkin', checkin: 'checkin', logs: 'logs', electrics: 'power', syslog: 'logs' }
// Switched with their capability, so not twice.
const IN_CAPABILITIES = new Set(['syslog', 'traffic', 'power'])

function Glyph({ id }: { id: string }) {
  const icon: Icon = pageIcon(PAGE[id] ?? id)
  return (
    <ThemeIcon variant="light" color="bit" size={28} radius="md" aria-hidden>
      {createElement(icon, { size: 17, stroke: 1.6 })}
    </ThemeIcon>
  )
}

/** What a capability still needs: done, missing (with where to do it), or outside Floorbit. */
function NeedLine({ need }: { need: Need }) {
  const { t } = useTranslation()
  const label = t(`features.cap.need.${need.id}`, { defaultValue: need.id })
  const Mark = need.ok === null ? IconInfoCircle : need.ok ? IconCircleCheck : IconCircleDashed
  const color = need.ok === null ? 'var(--mantine-color-dimmed)' : need.ok ? 'var(--mantine-color-up-filled)' : 'var(--mantine-color-warn-filled)'
  return (
    <Group gap={8} wrap="nowrap" align="flex-start" data-need={need.id} data-ok={String(need.ok)}>
      <Mark size={16} color={color} aria-hidden style={{ flex: 'none', marginTop: 3 }} />
      <div>
        {need.href && !need.ok
          ? (need.href.startsWith('#') ? <Anchor href={need.href} size="sm">{label}</Anchor>
            : <Anchor component={Link} to={need.href} size="sm">{label}</Anchor>)
          : <Text size="sm" c={need.ok ? 'dimmed' : undefined}>{label}</Text>}
        {need.ok === null && <Text size="xs" c="dimmed">{t('features.cap.outside')}</Text>}
      </div>
    </Group>
  )
}

/** What used to be Settings > Features (#1436): each built-in part of Floorbit as a card like a
 *  plugin's. A capability's switch has three states: on, partly (shown on, with what is off and a
 *  way to turn it all on) and off. */
export default function BuiltIn() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const caps = useQuery({ queryKey: capKey, queryFn: () => get<{ capabilities: Capability[] }>('/api/settings/capabilities') })
  const feats = useQuery({ queryKey: qk.featureSettings, queryFn: () => get<Features>('/api/settings/features') })
  // The other list and the links elsewhere follow; the one just answered is set from its answer.
  const changed = (other: readonly string[]) => {
    void qc.invalidateQueries({ queryKey: other, exact: true })
    void qc.invalidateQueries({ queryKey: qk.features, exact: true })
    void qc.invalidateQueries({ queryKey: qk.plugins })
  }
  useLiveEvent('features.changed', () => { changed(capKey); changed(qk.featureSettings) })
  const switchCap = useMutation({
    mutationFn: ({ id, on }: { id: string; on: boolean }) => put<{ capabilities: Capability[] }>(`/api/settings/capabilities/${id}`, { on }),
    onSuccess: (answer) => { qc.setQueryData(capKey, answer); changed(qk.featureSettings) },
  })
  const switchFeature = useMutation({
    mutationFn: (body: Record<string, boolean>) => put<Features>('/api/settings/features', body),
    onSuccess: (answer) => { qc.setQueryData(qk.featureSettings, answer); changed(capKey) },
  })
  const capName = (id: string) => t(`features.cap.name.${id}`)
  const featName = (id: string) => t(`features.name.${id}`, { defaultValue: id })
  const builtIn = t('plugins.trust.builtin')

  if (caps.isPending || feats.isPending) return <LoadingState rows={4} />
  const d = feats.data
  return (
    <Stack gap="lg">
      <Text size="sm" c="dimmed">{t('plugins.builtin.intro')}</Text>
      <ErrorBanner error={caps.error ?? feats.error ?? switchCap.error ?? switchFeature.error} />

      <Stack gap="sm">
        <Title order={2} fz="md">{t('features.cap.title')}</Title>
        <Text size="sm" c="dimmed">{t('features.cap.intro')}</Text>
        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md" component="ul" className="fb-plain-list">
          {(caps.data?.capabilities ?? []).map((c) => {
            const missing = c.needs.filter((n) => n.ok !== true)
            const offParts = c.parts.filter((p) => !p.on)
            return (
              <PluginCard key={c.id} id={`cap-${c.id}`} data-cap={c.id}
                head={<><Glyph id={c.id} /><Title order={3} fz="md" className="fb-plugin-card-name">{capName(c.id)}</Title></>}
                badge={<Badge variant="light" color={STATE_COLOR[c.state]} tt="none" style={{ flex: 'none' }}>{t(`features.cap.state.${c.state}`)}</Badge>}
                about={t(`features.cap.desc.${c.id}`)}
                foot={<>
                  <Text size="xs" c="dimmed" truncate>{builtIn}</Text>
                  <Switch size="md" aria-label={capName(c.id)} checked={c.state !== 'off'} disabled={c.forced_off || switchCap.isPending}
                    color={c.state === 'partly' ? 'warn' : undefined}
                    onChange={(e) => switchCap.mutate({ id: c.id, on: e.currentTarget.checked })} />
                </>}>
                {c.state === 'partly' && (
                  <Group gap="xs" wrap="nowrap" justify="space-between">
                    <Text size="xs" c="warn">
                      {t('features.cap.partly', { parts: offParts.map((p) => t(`features.cap.part.${p.id}`, { defaultValue: p.id })).join(', ') })}
                    </Text>
                    <Button size="compact-xs" variant="default" disabled={switchCap.isPending}
                      onClick={() => switchCap.mutate({ id: c.id, on: true })}>{t('features.cap.allOn')}</Button>
                  </Group>
                )}
                {c.forced_off && <Text size="xs" c="warn">{t('features.cap.forced')}</Text>}
                {c.state !== 'off' && missing.length > 0 && (
                  <Stack gap={4} aria-label={t('features.cap.stillNeeds', { name: capName(c.id) })}>
                    <Text size="xs" fw={600}>{t('features.cap.needsTitle')}</Text>
                    {c.needs.map((n) => <NeedLine key={n.id} need={n} />)}
                  </Stack>
                )}
              </PluginCard>
            )
          })}
        </SimpleGrid>
      </Stack>

      <Stack gap="sm">
        <Title order={2} fz="md">{t('features.others')}</Title>
        <Text size="sm" c="dimmed">{t('features.othersIntro')}</Text>
        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md" component="ul" className="fb-plain-list">
          {d && d.features.filter((f) => !IN_CAPABILITIES.has(f.id)).map((f) => {
            const blockedBy = f.needs.filter((n) => !d.features.find((o) => o.id === n)?.on)
            const state = f.on ? 'on' : 'off'
            return (
              <PluginCard key={f.id} id={`feature-${f.id}`} data-feature={f.id}
                head={<><Glyph id={f.id} /><Title order={3} fz="md" className="fb-plugin-card-name">{featName(f.id)}</Title></>}
                badge={<Badge variant="light" color={STATE_COLOR[state]} tt="none" style={{ flex: 'none' }}>{t(`features.cap.state.${state}`)}</Badge>}
                about={t(`features.desc.${f.id}`, { defaultValue: '' })}
                foot={<>
                  <Text size="xs" c="dimmed" truncate>{builtIn}</Text>
                  <Switch size="md" aria-label={featName(f.id)} checked={f.chosen && !f.forced_off} disabled={f.forced_off || switchFeature.isPending}
                    onChange={(e) => switchFeature.mutate({ [f.id]: e.currentTarget.checked })} />
                </>}>
                {f.forced_off && <Text size="xs" c="warn">{t('features.forced', { env: d.env })}</Text>}
                {!f.forced_off && f.chosen && blockedBy.length > 0 && (
                  <Text size="xs" c="warn">{t('features.needs', { names: blockedBy.map(featName).join(', ') })}</Text>
                )}
              </PluginCard>
            )
          })}
        </SimpleGrid>
      </Stack>
    </Stack>
  )
}
