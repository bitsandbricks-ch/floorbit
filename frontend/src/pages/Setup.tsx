import { Alert, Button, Group, Loader, PasswordInput, Stack, Text, TextInput } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type ChangeEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import { useSetup } from '@/api/queries'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ErrorBanner } from '@/components/ui'
import { SetupChecklist } from './setup/Checklist'

function AccountStep() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [form, setForm] = useState({ code: '', username: '', password: '', repeat: '' })
  const [error, setError] = useState<string | null>(null)
  const create = useMutation({
    mutationFn: () => post('/api/setup/account', { code: form.code, username: form.username, password: form.password }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.me })
      void client.invalidateQueries({ queryKey: qk.setup })
    },
    onError: (e) => setError(e.message),
  })
  const set = (k: keyof typeof form) => (e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.currentTarget.value })
  const mismatch = form.repeat !== '' && form.repeat !== form.password
  return (
    <form onSubmit={(e) => { e.preventDefault(); setError(null); create.mutate() }}>
      <Stack gap="sm" maw={420}>
        <Text>{t('setup.account.text')}</Text>
        <Text size="sm" c="dimmed">{t('setup.account.codeHelp')}</Text>
        <TextInput label={t('setup.account.code')} value={form.code} onChange={set('code')} required
          autoComplete="off" placeholder="ABCD-2345" />
        <TextInput label={t('setup.account.username')} value={form.username} onChange={set('username')} required
          autoComplete="username" />
        <PasswordInput label={t('setup.account.password')} description={t('setup.account.passwordHelp')}
          value={form.password} onChange={set('password')} required autoComplete="new-password" />
        <PasswordInput label={t('setup.account.repeat')} value={form.repeat} onChange={set('repeat')} required
          autoComplete="new-password" error={mismatch ? t('setup.account.mismatch') : undefined} />
        {error && <Alert color="down" role="alert">{error}</Alert>}
        <Group justify="flex-end">
          <Button type="submit" loading={create.isPending} disabled={mismatch}>{t('setup.account.create')}</Button>
        </Group>
      </Stack>
    </form>
  )
}

/** Ends the first-run setup: the floor plan stops sending admins here. The checklist stays. */
function Finish() {
  const { t } = useTranslation()
  const done = useMutation({ mutationFn: () => post('/api/setup/finish'), onSuccess: () => window.location.assign('/') })
  return (
    <Group justify="space-between" gap="sm">
      <Text size="sm" c="dimmed">{t('setup.finish.later')}</Text>
      {done.error && <Alert color="down" role="alert">{done.error.message}</Alert>}
      <Button onClick={() => done.mutate()} loading={done.isPending}>{t('setup.finish.open')}</Button>
    </Group>
  )
}

/** Set up (#988): the first admin account on a new install, then the steps an event needs, each
 *  done, needing a look or not started, and linking to the one place it is set. */
export default function Setup() {
  const { t } = useTranslation()
  const setup = useSetup()
  const data = setup.data

  let body
  if (setup.isPending || !data) body = <Loader size="sm" />
  else if (data.needs_account) body = <AccountStep />
  else if (!data.can_set_up) body = <Alert color="gray">{data.done ? t('setup.alreadyDone') : t('setup.adminOnly')}</Alert>
  else body = <Stack gap="md"><SetupChecklist />{!data.done && <Finish />}</Stack>

  return (
    <Layout title={t('setup.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('setup.title')} desc={data?.needs_account ? t('setup.introAccount') : t('setup.intro')} />
      <ErrorBanner error={setup.error} mb="md" />
      {body}
    </Layout>
  )
}
