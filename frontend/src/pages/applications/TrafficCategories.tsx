import { ActionIcon, Button, ColorSwatch, Group, Stack, Text, TextInput } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { qk } from '@/api/keys'
import {
  saveTrafficCategories, trafficCategoriesKey, useTrafficCategories, type OwnCategory,
} from '@/api/trafficCategories'
import { ErrorBanner, PanelSection, SidePanel, toastDone } from '@bitsandbricks/ui'

const slug = (name: string) => name.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 30)

/** The tenant's traffic categories beside the applications list (#1622): the built-in seven, and
 *  its own, the same for every event. Admins only. */
export function TrafficCategories({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const cats = useTrafficCategories()
  const saved = cats.list.filter((c) => !c.builtin).map((c) => ({ id: c.id, name: c.name, name_de: c.name_de, colour: c.colour }))
  const [own, setOwn] = useState<OwnCategory[] | null>(null)
  const list = own ?? saved
  const used = new Set(list.map((c) => c.colour))
  const nextColour = cats.palette.find((p) => !used.has(p)) ?? cats.palette[0] ?? '#78716c'
  const save = useMutation({
    mutationFn: () => saveTrafficCategories(list),
    onSuccess: (answer) => {
      client.setQueryData(trafficCategoriesKey, answer)
      void client.invalidateQueries({ queryKey: qk.applicationsAll })
      setOwn(null)
      toastDone(t('trafficCategories.saved'))
    },
  })
  const change = (i: number, patch: Partial<OwnCategory>) =>
    setOwn(list.map((c, j) => (j === i ? { ...c, ...patch } : c)))

  return (
    <SidePanel onClose={onClose} padded={false} title={t('trafficCategories.title')}
      footer={(
        <Group justify="flex-end">
          <Button loading={save.isPending} disabled={own === null} onClick={() => save.mutate()}>{t('trafficCategories.save')}</Button>
        </Group>
      )}>
      <PanelSection>
        <Text size="sm" c="dimmed">{t('trafficCategories.intro')}</Text>
      </PanelSection>
      {save.error && <PanelSection><ErrorBanner error={save.error} /></PanelSection>}
      <PanelSection label={t('trafficCategories.builtin')}>
        <Group gap="xs">
          {cats.list.filter((c) => c.builtin).map((c) => (
            <Group key={c.id} gap={6} wrap="nowrap">
              <ColorSwatch color={c.colour} size={12} />
              <Text size="sm">{cats.label(c.id)}</Text>
            </Group>
          ))}
        </Group>
      </PanelSection>
      <PanelSection label={t('trafficCategories.own')}>
        <Stack gap="md">
          {list.length === 0 && <Text size="sm" c="dimmed">{t('trafficCategories.none')}</Text>}
          {list.map((c, i) => (
            <Stack key={i} gap={6}>
              <Group gap="xs" align="flex-end" wrap="nowrap">
                <TextInput style={{ flex: 1 }} label={t('trafficCategories.name')} value={c.name} maxLength={40} required
                  onChange={(e) => {
                    const name = e.currentTarget.value
                    const fresh = !saved.some((s) => s.id === c.id)
                    change(i, { name, ...(fresh ? { id: slug(name) } : {}) })
                  }} />
                <TextInput style={{ flex: 1 }} label={t('trafficCategories.nameDe')} value={c.name_de} maxLength={40}
                  placeholder={c.name} onChange={(e) => change(i, { name_de: e.currentTarget.value })} />
                <ActionIcon variant="subtle" color="red" size="lg" aria-label={t('trafficCategories.remove', { name: c.name })}
                  onClick={() => setOwn(list.filter((_, j) => j !== i))}>×</ActionIcon>
              </Group>
              <Group gap={6} role="radiogroup" aria-label={t('trafficCategories.colour', { name: c.name })}>
                {cats.palette.map((p) => (
                  <ColorSwatch key={p} component="button" type="button" color={p} size={20} role="radio"
                    aria-checked={c.colour === p} aria-label={p} onClick={() => change(i, { colour: p })}
                    style={{ cursor: 'pointer', outline: c.colour === p ? '2px solid var(--mantine-color-text)' : undefined, outlineOffset: 2 }} />
                ))}
              </Group>
            </Stack>
          ))}
          {list.length < cats.maxOwn && (
            <Group>
              <Button variant="default" size="compact-sm"
                onClick={() => setOwn([...list, { id: '', name: '', name_de: '', colour: nextColour }])}>
                {t('trafficCategories.add')}
              </Button>
            </Group>
          )}
          <Text size="xs" c="dimmed">{t('trafficCategories.gone')}</Text>
        </Stack>
      </PanelSection>
    </SidePanel>
  )
}
