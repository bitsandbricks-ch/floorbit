import { ActionIcon, Alert, Button, FileButton, Group, Modal, SimpleGrid, Stack, Text, TextInput, Tooltip } from '@mantine/core'
import { IconCheck, IconUpload } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { CustomIcon } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { CustomIconGlyph } from './icons'
import { useCustomIcons } from './scope'

/** The shared icon library: admins upload SVGs (the server cleans them), everyone picks from it. */
export function IconLibrary({ opened, canManage, onClose }: { opened: boolean; canManage: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data } = useCustomIcons(opened)
  const [error, setError] = useState<string | null>(null)
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: qk.customIcons })
    void qc.invalidateQueries({ queryKey: qk.inventoryAll })
  }
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) {
        await post('/api/icons', { name: file.name.replace(/\.svg$/i, '').replace(/[-_]+/g, ' '), svg: await file.text() })
      }
    },
    onSuccess: () => { setError(null); refresh() },
    onError: (e) => { setError(e.message); refresh() },
  })
  const icons = data?.icons ?? []
  return (
    <Modal opened={opened} onClose={onClose} title={t('inventory.library.title')} size="lg">
      <Stack gap="sm">
        <Text size="sm" c="dimmed">{t('inventory.library.intro', { kb: data?.max_kb ?? 64 })}</Text>
        {canManage ? (
          <FileButton multiple accept="image/svg+xml,.svg" onChange={(files) => files.length && upload.mutate(files)}>
            {(props) => (
              <Button {...props} leftSection={<IconUpload size={16} />} loading={upload.isPending} style={{ alignSelf: 'flex-start' }}>
                {t('inventory.library.upload')}
              </Button>
            )}
          </FileButton>
        ) : <Text size="xs" c="dimmed">{t('inventory.library.adminsOnly')}</Text>}
        {error && <Alert color="down" role="alert">{error}</Alert>}
        {icons.length === 0 ? <Text size="sm" c="dimmed">{t('inventory.library.empty')}</Text> : (
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
            {icons.map((icon) => <IconRow key={icon.id} icon={icon} canManage={canManage} onChanged={refresh} onError={setError} />)}
          </SimpleGrid>
        )}
      </Stack>
    </Modal>
  )
}

function IconRow({ icon, canManage, onChanged, onError }: {
  icon: CustomIcon; canManage: boolean; onChanged: () => void; onError: (m: string) => void
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(icon.name)
  const rename = useMutation({
    mutationFn: () => patch(`/api/icons/${icon.id}`, { name }),
    onSuccess: onChanged,
    onError: (e) => onError(e.message),
  })
  const remove = useMutation({
    mutationFn: () => del(`/api/icons/${icon.id}`),
    onSuccess: onChanged,
    onError: (e) => onError(e.message),
  })
  return (
    <Group gap="xs" wrap="nowrap">
      <span style={{ color: 'var(--mantine-color-trace-6)', display: 'inline-flex' }}><CustomIconGlyph url={icon.url} size={28} label={icon.name} /></span>
      {canManage ? (
        <>
          <TextInput size="xs" style={{ flex: 1 }} value={name} maxLength={40} aria-label={t('inventory.library.name')}
            onChange={(e) => setName(e.currentTarget.value)}
            rightSection={name.trim() && name !== icon.name ? (
              <Tooltip label={t('inventory.save')}>
                <ActionIcon size="sm" variant="subtle" aria-label={t('inventory.save')} loading={rename.isPending} onClick={() => rename.mutate()}>
                  <IconCheck size={14} />
                </ActionIcon>
              </Tooltip>
            ) : undefined} />
          <ConfirmButton variant="subtle" danger size="xs" label={t('inventory.library.remove')}
            question={t('inventory.library.removeQ', { name: icon.name })} onConfirm={() => remove.mutate()} />
        </>
      ) : <Text size="sm">{icon.name}</Text>}
    </Group>
  )
}
