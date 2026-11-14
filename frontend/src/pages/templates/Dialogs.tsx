import { Alert, Button, FileInput, Group, Modal, Radio, Select, Stack, Text, TextInput, Textarea } from '@mantine/core'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { patch, post } from '@/api/client'
import type { ApplyResult, Hall, LayoutTemplate } from '@/api/types'
import { readText } from '../seatmap/model'

/** Save the floor plan, or one hall, as a new template or as a new version of one. */
export function SaveDialog({ halls, template, onClose, onDone }: {
  halls: Hall[]
  template?: LayoutTemplate
  onClose: () => void
  onDone: (t: LayoutTemplate) => void
}) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [hall, setHall] = useState('')
  const save = useMutation({
    mutationFn: () => template
      ? post<LayoutTemplate>(`/api/templates/${template.id}/versions`, { hall: hall || null })
      : post<LayoutTemplate>('/api/templates', { name, description, hall: hall || null }),
    onSuccess: onDone,
  })
  return (
    <Modal opened onClose={onClose} title={template ? t('templates.saveAgainTitle', { name: template.name }) : t('templates.saveTitle')} size="lg">
      <Stack gap="sm">
        {!template && (
          <>
            <TextInput label={t('templates.name')} value={name} onChange={(e) => setName(e.currentTarget.value)} maxLength={80} required data-autofocus />
            <Textarea label={t('templates.description')} value={description} onChange={(e) => setDescription(e.currentTarget.value)} maxLength={500} autosize minRows={2} />
          </>
        )}
        {template && <Text size="sm" c="dimmed">{t('templates.saveAgainHelp')}</Text>}
        {halls.length > 1 && (
          <Select label={t('templates.what')} value={hall} onChange={(v) => setHall(v ?? '')} allowDeselect={false}
            data={[{ value: '', label: t('templates.allHalls') }, ...halls.map((h) => ({ value: h.id, label: h.name }))]} />
        )}
        <Text size="sm" c="dimmed">{t('templates.noEventData')}</Text>
        {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
          <Button loading={save.isPending} disabled={!template && !name.trim()} onClick={() => save.mutate()}>{t('templates.save')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}

/** Start from a template: pick the version and, for a one-hall template, where it goes. */
export function ApplyDialog({ template, halls, onClose, onDone }: {
  template: LayoutTemplate
  halls: Hall[]
  onClose: () => void
  onDone: (r: ApplyResult) => void
}) {
  const { t } = useTranslation()
  const latest = template.versions[template.versions.length - 1]
  const [version, setVersion] = useState(String(latest.n))
  const chosen = template.versions.find((v) => String(v.n) === version) ?? latest
  const oneHall = chosen.halls === 1
  const [target, setTarget] = useState(oneHall && halls.length > 1 ? halls[0].id : '')
  const apply = useMutation({
    mutationFn: () => post<ApplyResult>(`/api/templates/${template.id}/apply`, { version: chosen.n, hall: oneHall && target ? target : null }),
    onSuccess: onDone,
  })
  const hallName = halls.find((h) => h.id === target)?.name ?? ''
  return (
    <Modal opened onClose={onClose} title={t('templates.applyTitle', { name: template.name })} size="lg">
      <Stack gap="sm">
        {template.versions.length > 1 && (
          <Select label={t('templates.version')} value={version} onChange={(v) => setVersion(v ?? String(latest.n))} allowDeselect={false}
            data={[...template.versions].reverse().map((v) => ({ value: String(v.n), label: t('templates.versionLabel', { n: v.n, saved: v.saved.slice(0, 16).replace('T', ' ') }) }))} />
        )}
        {oneHall && halls.length > 1 && (
          <Radio.Group label={t('templates.into')} value={target} onChange={setTarget}>
            <Stack gap={6} mt={6}>
              {halls.map((h) => <Radio key={h.id} value={h.id} label={h.name} />)}
              <Radio value="" label={t('templates.wholePlan')} />
            </Stack>
          </Radio.Group>
        )}
        <Alert color="warn" role="note">
          {oneHall && target ? t('templates.replacesHall', { hall: hallName }) : t('templates.replacesAll')}
        </Alert>
        {apply.error && <Alert color="down" role="alert">{apply.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
          <Button color="down" loading={apply.isPending} onClick={() => apply.mutate()}>{t('templates.applyNow')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}

export function EditDialog({ template, onClose, onDone }: { template: LayoutTemplate; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation()
  const [name, setName] = useState(template.name)
  const [description, setDescription] = useState(template.description)
  const save = useMutation({
    mutationFn: () => patch<LayoutTemplate>(`/api/templates/${template.id}`, { name, description }),
    onSuccess: onDone,
  })
  return (
    <Modal opened onClose={onClose} title={t('templates.editTitle')}>
      <Stack gap="sm">
        <TextInput label={t('templates.name')} value={name} onChange={(e) => setName(e.currentTarget.value)} maxLength={80} required data-autofocus />
        <Textarea label={t('templates.description')} value={description} onChange={(e) => setDescription(e.currentTarget.value)} maxLength={500} autosize minRows={2} />
        {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
          <Button loading={save.isPending} disabled={!name.trim()} onClick={() => save.mutate()}>{t('templates.save')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}

export function ImportDialog({ onClose, onDone }: { onClose: () => void; onDone: (t: LayoutTemplate) => void }) {
  const { t } = useTranslation()
  const [file, setFile] = useState<File | null>(null)
  const send = useMutation({
    mutationFn: async () => {
      let body: unknown
      try {
        body = JSON.parse(await readText(file!))
      } catch {
        throw new Error(t('templates.notJson'))
      }
      return post<LayoutTemplate>('/api/templates/import', body)
    },
    onSuccess: onDone,
  })
  return (
    <Modal opened onClose={onClose} title={t('templates.importTitle')}>
      <Stack gap="sm">
        <Text size="sm" c="dimmed">{t('templates.importHelp')}</Text>
        <FileInput label={t('templates.file')} accept=".json,application/json" value={file} onChange={setFile} clearable />
        {send.error && <Alert color="down" role="alert">{send.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
          <Button disabled={!file} loading={send.isPending} onClick={() => send.mutate()}>{t('templates.importNow')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}
