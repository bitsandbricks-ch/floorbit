import { Anchor, Button, Group, NumberInput, Stack, Switch, Text, TextInput } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  addRuleSource, changeRuleSource, fetchRuleSources, freezeRuleSources, removeRuleSource, ruleSourcesKey, syncRuleSource,
  type RuleSource,
} from '@/api/applicationSources'
import { qk } from '@/api/keys'
import { ConfirmButton, EmptyState, ErrorBanner, PanelSection, SidePanel, StatusBadge } from '@bitsandbricks/ui'
import { ago } from '@/lib/time'

/** The rule sources beside the applications list (docs/applications.md, "Rule sources"): files
 *  Floorbit fetches on a schedule, the freeze for the event, and adding one. Admins only. */
export function RuleSources({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const q = useQuery({ queryKey: ruleSourcesKey, queryFn: fetchRuleSources })
  const changed = () => {
    void client.invalidateQueries({ queryKey: ruleSourcesKey })
    void client.invalidateQueries({ queryKey: qk.applicationsAll })
    void client.invalidateQueries({ queryKey: qk.gamesAll })
  }
  const freeze = useMutation({ mutationFn: freezeRuleSources, onSuccess: changed })
  const list = q.data?.sources ?? []
  const frozen = !!q.data?.frozen

  return (
    <SidePanel onClose={onClose} padded={false} title={t('applicationSources.title')}
      resizable={{ storageKey: 'floorbit.ruleSourcesPanel.width' }}>
      <PanelSection>
        <Text size="sm" c="dimmed">{t('applicationSources.intro')}</Text>
      </PanelSection>
      {(q.error || freeze.error) && <PanelSection><ErrorBanner error={q.error ?? freeze.error} /></PanelSection>}
      <PanelSection>
        <Switch checked={frozen} disabled={!q.data || freeze.isPending} onChange={(e) => freeze.mutate(e.currentTarget.checked)}
          label={t('applicationSources.freeze')} description={t('applicationSources.freezeHelp')} />
      </PanelSection>
      <PanelSection label={t('applicationSources.list')}>
        {list.length === 0 && !q.isLoading
          ? <EmptyState title={t('applicationSources.none')} />
          : (
            <Stack gap="md">
              {list.map((s, i) => (
                <SourceRow key={s.id} source={s} first={i === 0} frozen={frozen} onChanged={changed} />
              ))}
            </Stack>
          )}
      </PanelSection>
      <PanelSection label={t('applicationSources.add')}>
        <AddSource onAdded={changed} />
      </PanelSection>
    </SidePanel>
  )
}

function SourceRow({ source: s, first, frozen, onChanged }: {
  source: RuleSource; first: boolean; frozen: boolean; onChanged: () => void
}) {
  const { t } = useTranslation()
  const change = useMutation({ mutationFn: (body: Parameters<typeof changeRuleSource>[1]) => changeRuleSource(s.id, body), onSuccess: onChanged })
  const sync = useMutation({ mutationFn: () => syncRuleSource(s.id), onSuccess: onChanged })
  const remove = useMutation({ mutationFn: () => removeRuleSource(s.id), onSuccess: onChanged })
  const state = !s.on ? <StatusBadge tone="off" label={t('applicationSources.off')} />
    : s.ok === null ? <StatusBadge tone="off" label={t('applicationSources.notYet')} />
    : s.ok ? <StatusBadge tone="ok" label={t('applicationSources.ok', { count: s.count })} />
    : <StatusBadge tone="err" label={t('applicationSources.failed')} />
  const error = change.error ?? sync.error ?? remove.error

  return (
    <Stack gap={4} aria-label={s.name}>
      <Group justify="space-between" wrap="nowrap" gap="xs">
        <Text size="sm" fw={600} truncate>{s.name}</Text>
        {state}
      </Group>
      <Text size="xs" c="dimmed" ff="monospace" truncate>{s.url}</Text>
      {s.builtin && <Text size="xs" c="dimmed">{t('applicationSources.ownList')}</Text>}
      <Text size="xs" c="dimmed">
        {t('applicationSources.every', { count: s.every_hours })}
        {' · '}{t('applicationSources.fetched', { when: ago(s.at) })}
        {' · '}{t('applicationSources.changed', { when: ago(s.changed_at) })}
      </Text>
      {s.last_change && <LastChange change={s.last_change} />}
      {s.ok === false && s.error && (
        <Text size="xs" c="var(--bnb-err)">{s.count ? t('applicationSources.keptCopy', { error: s.error }) : s.error}</Text>
      )}
      {error && <ErrorBanner error={error} />}
      <Group gap="xs">
        <Switch size="xs" checked={s.on} label={t('applicationSources.on')} disabled={change.isPending}
          onChange={(e) => change.mutate({ on: e.currentTarget.checked })} />
        <Button size="compact-xs" variant="default" disabled={frozen || !s.on} loading={sync.isPending}
          title={frozen ? t('applicationSources.frozenHint') : undefined} onClick={() => sync.mutate()}>
          {t('applicationSources.syncNow')}
        </Button>
        {!first && !s.builtin && (
          <Button size="compact-xs" variant="subtle" onClick={() => change.mutate({ position: 0 })}>
            {t('applicationSources.top')}
          </Button>
        )}
        {!s.builtin && (
          <ConfirmButton size="compact-xs" variant="subtle" danger label={t('applicationSources.remove')}
            question={t('applicationSources.removeAsk', { name: s.name })} onConfirm={() => remove.mutate()} />
        )}
      </Group>
    </Stack>
  )
}

/** What the last fetch that changed something brought: counts, and the names on demand. */
function LastChange({ change }: { change: NonNullable<RuleSource['last_change']> }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const parts = (['added', 'changed', 'removed'] as const)
  const any = parts.some((k) => change[k].count)
  if (!any) return null
  return (
    <div>
      <Anchor component="button" type="button" size="xs" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {t('applicationSources.lastChange', { added: change.added.count, changed: change.changed.count, removed: change.removed.count })}
      </Anchor>
      {open && parts.filter((k) => change[k].count).map((k) => (
        <Text key={k} size="xs" c="dimmed">
          {t(`applicationSources.change.${k}`)}: {change[k].names.join(', ')}
          {change[k].count > change[k].names.length && ` ${t('applicationSources.andMore', { count: change[k].count - change[k].names.length })}`}
        </Text>
      ))}
    </div>
  )
}

function AddSource({ onAdded }: { onAdded: () => void }) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [every, setEvery] = useState<number>(24)
  const add = useMutation({
    mutationFn: () => addRuleSource({ name, url, every_hours: every }),
    onSuccess: () => { setName(''); setUrl(''); setEvery(24); onAdded() },
  })
  return (
    <Stack gap="sm">
      {add.error && <ErrorBanner error={add.error} />}
      <TextInput label={t('applicationSources.name')} value={name} maxLength={60} onChange={(e) => setName(e.currentTarget.value)} />
      <TextInput label={t('applicationSources.url')} description={t('applicationSources.urlHelp')} value={url}
        placeholder="https://example.com/rules.json" onChange={(e) => setUrl(e.currentTarget.value)} />
      <NumberInput label={t('applicationSources.everyLabel')} min={1} max={720} value={every}
        onChange={(v) => setEvery(typeof v === 'number' ? v : 24)} />
      <Group justify="flex-end">
        <Button loading={add.isPending} disabled={!name.trim() || !url.trim()} onClick={() => add.mutate()}>
          {t('applicationSources.addButton')}
        </Button>
      </Group>
    </Stack>
  )
}
