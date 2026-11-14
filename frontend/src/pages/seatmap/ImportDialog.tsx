import { Button, Checkbox, FileInput, Group, List, Modal, Stack, Text } from '@mantine/core'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, post } from '@/api/client'
import type { ImportResult } from '@/api/types'
import { readText } from './model'

export function ImportDialog({ opened, onClose, onDone }: { opened: boolean; onClose: () => void; onDone: (r: ImportResult) => void }) {
  const { t } = useTranslation()
  const [file, setFile] = useState<File | null>(null)
  const [replace, setReplace] = useState(false)
  const [preview, setPreview] = useState<ImportResult | null>(null)
  const [problems, setProblems] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  const send = useMutation({
    mutationFn: async (dryRun: boolean) => post<ImportResult>('/api/seat-map/import', { csv: await readText(file!), replace, dry_run: dryRun }),
    onSuccess: (r, dryRun) => {
      setError(null)
      setProblems([])
      if (dryRun) setPreview(r)
      else onDone(r)
    },
    onError: (e) => {
      setPreview(null)
      setError(e.message)
      const p = e instanceof ApiError ? e.data.problems : undefined
      setProblems(Array.isArray(p) ? p.map(String) : [])
    },
  })

  const reset = () => setPreview(null)
  return (
    <Modal opened={opened} onClose={onClose} title={t('seatmap.importTitle')} size="lg">
      <Stack gap="sm">
        <Text size="sm" c="dimmed">
          {t('seatmap.importHelp')}
        </Text>
        <FileInput
          label={t('seatmap.file')}
          accept=".csv,text/csv"
          value={file}
          onChange={(f) => {
            setFile(f)
            reset()
          }}
          clearable
        />
        <Checkbox
          label={t('seatmap.replace')}
          checked={replace}
          onChange={(e) => {
            setReplace(e.currentTarget.checked)
            reset()
          }}
        />
        {error && (
          <div role="alert">
            <Text className="fb-tone-err">✕ {error}</Text>
            {problems.length > 0 && (
              <List size="sm" mt={4}>
                {problems.map((p) => (
                  <List.Item key={p}>{p}</List.Item>
                ))}
              </List>
            )}
          </div>
        )}
        {preview && <Text role="status">{t('seatmap.preview', { ...preview })}</Text>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          {preview ? (
            <Button color={replace && preview.removed ? 'down' : undefined} loading={send.isPending} onClick={() => send.mutate(false)}>
              {t('seatmap.importNow')}
            </Button>
          ) : (
            <Button disabled={!file} loading={send.isPending} onClick={() => send.mutate(true)}>
              {t('seatmap.check')}
            </Button>
          )}
        </Group>
      </Stack>
    </Modal>
  )
}
