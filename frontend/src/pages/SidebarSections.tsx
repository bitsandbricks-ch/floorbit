import { ActionIcon, Button, Group, SegmentedControl, Stack, Text, TextInput, Tooltip } from '@mantine/core'
import { IconArrowDown, IconArrowUp, IconPlus, IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, put } from '@/api/client'
import { qk } from '@/api/keys'
import { EntitySelect } from '@/components/EntitySelect'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { EmptyState, ErrorBanner, LoadingState, Panel } from '@/components/ui'
import { CUSTOM_ICONS } from '@/nav/sections'

type Kind = 'dashboard' | 'page' | 'url'
interface Link { kind: Kind; ref?: string; href?: string; label?: string }
interface Section { id: string; name: string; icon: string; links: Link[] }
interface Answer { sections: Section[]; icons: string[] }

const MAX_SECTIONS = 12
const MAX_LINKS = 20

function move<T>(list: T[], from: number, by: number): T[] {
  const to = from + by
  if (to < 0 || to >= list.length) return list
  const next = [...list]
  ;[next[from], next[to]] = [next[to], next[from]]
  return next
}

/** Sidebar sections of your own (floorbit/nav_sections.py): a name, an icon and links to dashboards,
 *  pages or addresses. Everyone sees them in the sidebar, each with only the links they may open. */
export default function SidebarSections() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.sidebarSections, queryFn: () => get<Answer>('/api/settings/sidebar') })
  // The edits not saved yet; null while nothing changed, so a save elsewhere shows up here.
  const [draft, setDraft] = useState<Section[] | null>(null)
  const sections = draft ?? query.data?.sections ?? []
  const save = useMutation({
    mutationFn: (body: Section[]) => put<Answer>('/api/settings/sidebar', { sections: body }),
    onSuccess: (answer) => {
      qc.setQueryData(qk.sidebarSections, answer)
      setDraft(null)
      void qc.invalidateQueries({ queryKey: qk.pages, exact: true })   // the sidebar itself
    },
  })
  const icons = query.data?.icons ?? Object.keys(CUSTOM_ICONS)

  const set = (next: Section[]) => setDraft(next)
  const setSection = (i: number, patch: Partial<Section>) => set(sections.map((s, n) => (n === i ? { ...s, ...patch } : s)))
  const setLink = (i: number, j: number, patch: Partial<Link>) =>
    setSection(i, { links: sections[i].links.map((l, n) => (n === j ? { ...l, ...patch } : l)) })
  const addSection = () => set([...sections, { id: '', name: '', icon: 'dashboard', links: [{ kind: 'dashboard' }] }])

  return (
    <Layout title={t('sidebarSections.title')} back={{ href: '/settings', label: t('sidebarSections.settings') }}>
      <PageHead
        title={t('sidebarSections.title')} desc={t('sidebarSections.intro')}
        actions={(
          <Group gap="xs">
            {draft && <Button variant="default" onClick={() => setDraft(null)} disabled={save.isPending}>{t('sidebarSections.discard')}</Button>}
            <Button onClick={() => save.mutate(sections)} loading={save.isPending} disabled={!draft}>{t('sidebarSections.save')}</Button>
          </Group>
        )}
      />
      <Stack gap="md">
        <ErrorBanner error={query.error ?? save.error} />
        {query.isPending ? <LoadingState /> : (
          <>
            {sections.length === 0 && (
              <EmptyState title={t('sidebarSections.emptyTitle')} desc={t('sidebarSections.emptyDesc')} />
            )}
            {sections.map((s, i) => (
              <Panel
                key={i} aria-label={s.name || t('sidebarSections.unnamed')}
                title={s.name || t('sidebarSections.unnamed')}
                actions={(
                  <>
                    <Tooltip label={t('sidebarSections.up')}>
                      <ActionIcon variant="subtle" aria-label={t('sidebarSections.up')} disabled={i === 0} onClick={() => set(move(sections, i, -1))}>
                        <IconArrowUp size={16} aria-hidden="true" />
                      </ActionIcon>
                    </Tooltip>
                    <Tooltip label={t('sidebarSections.down')}>
                      <ActionIcon variant="subtle" aria-label={t('sidebarSections.down')} disabled={i === sections.length - 1} onClick={() => set(move(sections, i, 1))}>
                        <IconArrowDown size={16} aria-hidden="true" />
                      </ActionIcon>
                    </Tooltip>
                    <Tooltip label={t('sidebarSections.remove')}>
                      <ActionIcon variant="subtle" color="down" aria-label={t('sidebarSections.remove')} onClick={() => set(sections.filter((_, n) => n !== i))}>
                        <IconTrash size={16} aria-hidden="true" />
                      </ActionIcon>
                    </Tooltip>
                  </>
                )}
              >
                <Stack gap="sm">
                  <TextInput
                    label={t('sidebarSections.name')} required maxLength={40} value={s.name}
                    placeholder={t('sidebarSections.namePlaceholder')}
                    onChange={(e) => setSection(i, { name: e.currentTarget.value })}
                  />
                  <div>
                    <Text size="sm" fw={500} mb={4} id={`icon-${i}`}>{t('sidebarSections.icon')}</Text>
                    <Group gap={4} role="radiogroup" aria-labelledby={`icon-${i}`}>
                      {icons.map((name) => {
                        const Icon = CUSTOM_ICONS[name]
                        if (!Icon) return null
                        const label = t(`sidebarSections.icons.${name}`, { defaultValue: name })
                        return (
                          <Tooltip key={name} label={label}>
                            <ActionIcon
                              role="radio" aria-checked={s.icon === name} aria-label={label} size="lg"
                              variant={s.icon === name ? 'filled' : 'subtle'} onClick={() => setSection(i, { icon: name })}
                            >
                              <Icon size={18} aria-hidden="true" />
                            </ActionIcon>
                          </Tooltip>
                        )
                      })}
                    </Group>
                  </div>
                  <Text size="sm" fw={500}>{t('sidebarSections.links')}</Text>
                  {s.links.length === 0 && <Text size="sm" c="dimmed">{t('sidebarSections.noLinks')}</Text>}
                  {s.links.map((l, j) => (
                    <Group key={j} gap="xs" align="flex-end" wrap="wrap">
                      <SegmentedControl
                        size="xs" value={l.kind} aria-label={t('sidebarSections.kind')}
                        data={(['dashboard', 'page', 'url'] as const).map((k) => ({ value: k, label: t(`sidebarSections.kinds.${k}`) }))}
                        onChange={(v) => setLink(i, j, { kind: v as Kind, ref: undefined, href: undefined })}
                      />
                      {l.kind === 'url' ? (
                        <TextInput
                          style={{ flex: '2 1 220px' }} label={t('sidebarSections.address')} required value={l.href ?? ''}
                          placeholder="https://example.com" onChange={(e) => setLink(i, j, { href: e.currentTarget.value })}
                        />
                      ) : (
                        <EntitySelect
                          style={{ flex: '2 1 220px' }} kind={l.kind === 'dashboard' ? 'dashboards' : 'pages'} required
                          label={t(l.kind === 'dashboard' ? 'sidebarSections.dashboard' : 'sidebarSections.page')}
                          value={l.ref} onChange={(v) => setLink(i, j, { ref: v })}
                        />
                      )}
                      <TextInput
                        style={{ flex: '1 1 160px' }} label={t('sidebarSections.label')} maxLength={60} value={l.label ?? ''}
                        required={l.kind === 'url'} placeholder={l.kind === 'url' ? '' : t('sidebarSections.labelPlaceholder')}
                        onChange={(e) => setLink(i, j, { label: e.currentTarget.value })}
                      />
                      <Group gap={2} wrap="nowrap">
                        <ActionIcon variant="subtle" aria-label={t('sidebarSections.linkUp')} disabled={j === 0}
                          onClick={() => setSection(i, { links: move(s.links, j, -1) })}>
                          <IconArrowUp size={16} aria-hidden="true" />
                        </ActionIcon>
                        <ActionIcon variant="subtle" aria-label={t('sidebarSections.linkDown')} disabled={j === s.links.length - 1}
                          onClick={() => setSection(i, { links: move(s.links, j, 1) })}>
                          <IconArrowDown size={16} aria-hidden="true" />
                        </ActionIcon>
                        <ActionIcon variant="subtle" color="down" aria-label={t('sidebarSections.removeLink')}
                          onClick={() => setSection(i, { links: s.links.filter((_, n) => n !== j) })}>
                          <IconTrash size={16} aria-hidden="true" />
                        </ActionIcon>
                      </Group>
                    </Group>
                  ))}
                  <Group>
                    <Button
                      variant="light" size="xs" leftSection={<IconPlus size={14} aria-hidden="true" />} disabled={s.links.length >= MAX_LINKS}
                      onClick={() => setSection(i, { links: [...s.links, { kind: 'dashboard' }] })}
                    >
                      {t('sidebarSections.addLink')}
                    </Button>
                  </Group>
                </Stack>
              </Panel>
            ))}
            <Group>
              <Button variant="light" leftSection={<IconPlus size={16} aria-hidden="true" />} onClick={addSection} disabled={sections.length >= MAX_SECTIONS}>
                {t('sidebarSections.add')}
              </Button>
            </Group>
          </>
        )}
      </Stack>
    </Layout>
  )
}
