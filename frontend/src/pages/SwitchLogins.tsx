import { Alert, Button, Group, Paper, PasswordInput, SimpleGrid, Stack, Table, Text, TextInput, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, put } from '@/api/client'
import { qk } from '@/api/keys'
import type { StoredLogin } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { dateTime } from '@/lib/time'

/** Switch logins Floorbit keeps, encrypted and write-only (issue #474). */
export default function SwitchLogins() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const list = useQuery({ queryKey: qk.credentials, queryFn: () => get<{ credentials: StoredLogin[] }>('/api/settings/credentials') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.credentials })
  const [form, setForm] = useState({ scope: '*', username: '', password: '' })
  const save = useMutation({
    mutationFn: () => put<StoredLogin>('/api/settings/credentials/ssh', form),
    // The password leaves the page as soon as it is stored.
    onSuccess: () => { setForm((f) => ({ ...f, password: '' })); refresh() },
  })
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/settings/credentials/${id}`), onSuccess: refresh })
  const rows = list.data?.credentials ?? []
  const when = (s: number) => dateTime(s)
  return (
    <Layout title={t('switchLogins.title')}>
      <PageHead title={t('switchLogins.title')} desc={t('switchLogins.intro')} />
      <Stack gap="md">
        <Paper withBorder radius="lg" p="md">
          {rows.length === 0 ? <Text c="dimmed">{t('switchLogins.empty')}</Text> : (
            <Table.ScrollContainer minWidth={340}>
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('switchLogins.scope')}</Table.Th><Table.Th>{t('switchLogins.username')}</Table.Th>
                    <Table.Th visibleFrom="sm">{t('switchLogins.password')}</Table.Th>
                    <Table.Th visibleFrom="sm">{t('switchLogins.set')}</Table.Th><Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {rows.map((c) => (
                    <Table.Tr key={c.id}>
                      <Table.Td ff="monospace" style={{ whiteSpace: 'nowrap' }}>{c.scope}</Table.Td>
                      <Table.Td ff="monospace" style={{ whiteSpace: 'nowrap' }}>{c.username}</Table.Td>
                      <Table.Td c="dimmed" visibleFrom="sm">{t('switchLogins.hidden')}</Table.Td>
                      <Table.Td visibleFrom="sm"><Text size="sm">{when(c.set_at)}{c.set_by ? ` · ${c.set_by}` : ''}</Text></Table.Td>
                      <Table.Td>
                        <Group gap={6} justify="flex-end" wrap="nowrap">
                          <Button size="compact-sm" variant="default"
                            onClick={() => setForm({ scope: c.scope, username: c.username, password: '' })}>{t('switchLogins.replace')}</Button>
                          <ConfirmButton size="compact-sm" variant="subtle" danger label={t('switchLogins.remove')}
                            question={t('switchLogins.removeQuestion', { scope: c.scope })} onConfirm={() => remove.mutate(c.id)} />
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </Paper>
        <Paper withBorder radius="lg" p="md">
          <Stack gap="sm">
            <Title order={3} size="h4">{t('switchLogins.setTitle')}</Title>
            <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
              <TextInput label={t('switchLogins.scope')} description={t('switchLogins.scopeHint')} value={form.scope}
                inputWrapperOrder={['label', 'input', 'description']}
                onChange={(e) => setForm({ ...form, scope: e.currentTarget.value })} />
              <TextInput label={t('switchLogins.username')} autoComplete="off" value={form.username}
                onChange={(e) => setForm({ ...form, username: e.currentTarget.value })} />
              <PasswordInput label={t('switchLogins.password')} autoComplete="new-password" value={form.password}
                onChange={(e) => setForm({ ...form, password: e.currentTarget.value })} />
            </SimpleGrid>
            {(save.error || remove.error) && <Alert color="down" role="alert">{(save.error || remove.error)!.message}</Alert>}
            {save.isSuccess && <Alert color="up">{t('switchLogins.saved', { scope: save.data.scope })}</Alert>}
            <Group justify="flex-end">
              <Button loading={save.isPending} disabled={!form.scope.trim() || !form.username.trim() || !form.password}
                onClick={() => save.mutate()}>{t('switchLogins.save')}</Button>
            </Group>
            <Text size="sm" c="dimmed">{t('switchLogins.how')}</Text>
          </Stack>
        </Paper>
      </Stack>
    </Layout>
  )
}
