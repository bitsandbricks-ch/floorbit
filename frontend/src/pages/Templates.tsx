import { Alert, Anchor, Badge, Button, Group, Loader, Paper, Stack, Text, Title } from '@mantine/core'
import { IconDownload, IconFileImport, IconTemplate } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { Hall, LayoutTemplate } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ApplyDialog, EditDialog, ImportDialog, SaveDialog } from './templates/Dialogs'

type Open =
  | { kind: 'save'; template?: LayoutTemplate }
  | { kind: 'apply' | 'edit'; template: LayoutTemplate }
  | { kind: 'import' }
  | null

function TemplateCard({ tpl, canEdit, onOpen, onDuplicate, onDelete }: {
  tpl: LayoutTemplate
  canEdit: boolean
  onOpen: (o: Open) => void
  onDuplicate: () => void
  onDelete: () => void
}) {
  const { t } = useTranslation()
  const latest = tpl.versions[tpl.versions.length - 1]
  return (
    <Paper withBorder radius="lg" p="md" component="article" aria-labelledby={`tpl-${tpl.id}`}>
      <Group justify="space-between" align="flex-start" gap="sm">
        <Stack gap={4} style={{ flex: '1 1 280px', minWidth: 0 }}>
          <Title order={2} size="h4" id={`tpl-${tpl.id}`}>
            <IconTemplate size={18} style={{ verticalAlign: '-3px' }} aria-hidden="true" /> {tpl.name}
          </Title>
          {tpl.description && <Text size="sm">{tpl.description}</Text>}
          <Group gap={6}>
            <Badge variant="light" color="gray">{t('templates.halls', { count: latest.halls })}</Badge>
            <Badge variant="light" color="gray">{t('templates.switches', { count: latest.switches })}</Badge>
            <Badge variant="light" color="gray">{t('templates.blocks', { count: latest.seat_blocks })}</Badge>
          </Group>
          <Text size="xs" c="dimmed">
            {t('templates.versions')}{' '}
            {[...tpl.versions].reverse().map((v, i) => (
              <span key={v.n}>
                {i > 0 && ' · '}
                <Anchor href={`/api/templates/${tpl.id}/export?version=${v.n}`} size="xs" title={t('templates.exportVersion', { n: v.n })}>
                  {t('templates.versionLabel', { n: v.n, saved: v.saved.slice(0, 16).replace('T', ' ') })}
                </Anchor>
              </span>
            ))}
          </Text>
        </Stack>
        <Group gap="xs" justify="flex-end">
          {canEdit && <Button size="xs" color="down" variant="light" onClick={() => onOpen({ kind: 'apply', template: tpl })}>{t('templates.apply')}</Button>}
          {canEdit && <Button size="xs" variant="default" onClick={() => onOpen({ kind: 'save', template: tpl })}>{t('templates.saveAgain')}</Button>}
          <Button size="xs" variant="default" component="a" href={`/api/templates/${tpl.id}/export`} leftSection={<IconDownload size={14} />}>
            {t('templates.export')}
          </Button>
          {canEdit && <Button size="xs" variant="default" onClick={() => onOpen({ kind: 'edit', template: tpl })}>{t('templates.edit')}</Button>}
          {canEdit && <Button size="xs" variant="default" onClick={onDuplicate}>{t('templates.duplicate')}</Button>}
          {canEdit && <ConfirmButton size="xs" variant="subtle" danger label={t('templates.delete')} question={t('templates.deleteQuestion', { name: tpl.name })} onConfirm={onDelete} />}
        </Group>
      </Group>
    </Paper>
  )
}

export default function Templates() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canEdit = useCan('floorplan.edit')
  const [open, setOpen] = useState<Open>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const list = useQuery({ queryKey: qk.templates, queryFn: () => get<{ templates: LayoutTemplate[] }>('/api/templates') })
  const halls = useQuery({ queryKey: qk.halls, queryFn: () => get<{ halls: Hall[] }>('/api/halls') })
  const refresh = () => qc.invalidateQueries({ queryKey: qk.templates })
  const done = (message: string) => {
    setOpen(null)
    setNotice(message)
    void refresh()
  }
  const duplicate = useMutation({
    mutationFn: (tpl: LayoutTemplate) => post<LayoutTemplate>(`/api/templates/${tpl.id}/duplicate`),
    onSuccess: (copy) => done(t('templates.duplicated', { name: copy.name })),
  })
  const remove = useMutation({
    mutationFn: (tpl: LayoutTemplate) => del(`/api/templates/${tpl.id}`),
    onSuccess: (_r, tpl) => done(t('templates.deleted', { name: tpl.name })),
  })
  const hallList = halls.data?.halls ?? []
  const error = list.error ?? duplicate.error ?? remove.error

  return (
    <Layout title={t('templates.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead
        title={t('templates.title')}
        desc={t('templates.intro')}
        actions={canEdit && (
          <>
            <Button variant="default" leftSection={<IconFileImport size={16} />} onClick={() => setOpen({ kind: 'import' })}>{t('templates.import')}</Button>
            <Button onClick={() => setOpen({ kind: 'save' })}>{t('templates.saveCurrent')}</Button>
          </>
        )}
      />
      <Stack gap="md">
        {notice && <Alert color="up" role="status" withCloseButton onClose={() => setNotice(null)}>{notice}</Alert>}
        {error && <Alert color="down" role="alert">{t('common.error', { message: error.message })}</Alert>}
        {list.isPending ? (
          <Loader aria-label={t('common.loading')} />
        ) : !list.data?.templates.length ? (
          <Paper withBorder radius="lg" p="lg"><Text c="dimmed">{t('templates.empty')}</Text></Paper>
        ) : (
          list.data.templates.map((tpl) => (
            <TemplateCard key={tpl.id} tpl={tpl} canEdit={canEdit} onOpen={setOpen}
              onDuplicate={() => duplicate.mutate(tpl)} onDelete={() => remove.mutate(tpl)} />
          ))
        )}
      </Stack>

      {open?.kind === 'save' && (
        <SaveDialog halls={hallList} template={open.template} onClose={() => setOpen(null)}
          onDone={(tpl) => done(open.template ? t('templates.savedVersion', { name: tpl.name, n: tpl.versions[tpl.versions.length - 1].n }) : t('templates.saved', { name: tpl.name }))} />
      )}
      {open?.kind === 'apply' && (
        <ApplyDialog template={open.template} halls={hallList} onClose={() => setOpen(null)}
          onDone={(r) => {
            done(t('templates.applied', { ...r }))
            void qc.invalidateQueries({ queryKey: qk.halls })
          }} />
      )}
      {open?.kind === 'edit' && <EditDialog template={open.template} onClose={() => setOpen(null)} onDone={() => done(t('templates.changed'))} />}
      {open?.kind === 'import' && (
        <ImportDialog onClose={() => setOpen(null)}
          onDone={(tpl) => done(tpl.dropped?.length ? t('templates.importedDropped', { name: tpl.name, fields: tpl.dropped.join(', ') }) : t('templates.imported', { name: tpl.name }))} />
      )}
    </Layout>
  )
}
