import { Alert, Anchor, Button, Checkbox, Group, Loader, PasswordInput, Radio, Stack, Stepper, Text, TextInput } from '@mantine/core'
import { IconCheck, IconPlugConnected } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type ChangeEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useSetup } from '@/api/queries'
import type { ConnectionTest, SetupState, SetupStep } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

const STEPS: SetupStep[] = ['netbox', 'librenms', 'switches', 'theme']
const THEMES = ['floorbit', 'ops', 'kiosk', 'classic'] as const

/** Skip or continue: both record the step, so the wizard opens where it was left. */
function StepButtons({ step, busy, onSave, saveLabel, onDone }: {
  step: SetupStep
  busy?: boolean
  onSave?: () => Promise<unknown>
  saveLabel?: string
  onDone: () => void
}) {
  const { t } = useTranslation()
  const [error, setError] = useState<string | null>(null)
  const mark = useMutation({
    mutationFn: async (state: 'done' | 'skipped') => {
      if (state === 'done' && onSave) await onSave()
      return post(`/api/setup/steps/${step}`, { state })
    },
    onSuccess: () => { setError(null); onDone() },
    onError: (e) => setError(e.message),
  })
  return (
    <Stack gap="xs">
      {error && <Alert color="down" role="alert">{error}</Alert>}
      <Group justify="space-between">
        <Button variant="subtle" color="gray" onClick={() => mark.mutate('skipped')} disabled={mark.isPending}>
          {t('setup.skip')}
        </Button>
        <Button onClick={() => mark.mutate('done')} loading={mark.isPending} disabled={busy}>
          {saveLabel ?? t('setup.continue')}
        </Button>
      </Group>
    </Stack>
  )
}

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

function ConnectionStep({ service, connected, onDone }: { service: 'netbox' | 'librenms'; connected: boolean; onDone: () => void }) {
  const { t } = useTranslation()
  const [url, setUrl] = useState('')
  const [token, setToken] = useState('')
  const [verify, setVerify] = useState(true)
  const body = { [`${service}.url`]: url, [`${service}.token`]: token, [`${service}.verify_ssl`]: verify }
  const test = useMutation({ mutationFn: () => post<ConnectionTest>(`/api/settings/test/${service}`, body) })
  const filled = url.trim() !== '' && token.trim() !== ''
  return (
    <Stack gap="sm" maw={520}>
      <Text>{t(`setup.${service}.text`)}</Text>
      {connected && <Alert color="up" icon={<IconCheck size={16} />}>{t('setup.connected')}</Alert>}
      <TextInput label={t('setup.url')} placeholder={`https://${service}.example.com`} value={url}
        onChange={(e) => setUrl(e.currentTarget.value)} type="url" />
      <PasswordInput label={t('setup.token')} description={t(`setup.${service}.tokenHelp`)} value={token}
        onChange={(e) => setToken(e.currentTarget.value)} autoComplete="off" />
      <Checkbox label={t('setup.verify')} checked={verify} onChange={(e) => setVerify(e.currentTarget.checked)} />
      <Group>
        <Button variant="default" leftSection={<IconPlugConnected size={16} />} onClick={() => test.mutate()}
          loading={test.isPending} disabled={!filled}>{t('setup.test')}</Button>
        {test.data && (
          <Text size="sm" c={test.data.ok ? 'up' : 'down'} role="status">{test.data.message}</Text>
        )}
      </Group>
      <StepButtons step={service} onDone={onDone} busy={!filled && !connected}
        saveLabel={filled ? t('setup.saveContinue') : t('setup.continue')}
        onSave={filled ? () => put('/api/settings', body) : undefined} />
    </Stack>
  )
}

function SwitchesStep({ setup, onDone }: { setup: SetupState; onDone: () => void }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const sync = useMutation({
    mutationFn: () => post<unknown[]>('/api/switches/sync'),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.setup }),
  })
  const total = setup.switches?.total ?? 0
  return (
    <Stack gap="sm" maw={520}>
      {setup.netbox ? (
        <>
          <Text>{t('setup.switches.netbox')}</Text>
          <Group>
            <Button variant="default" onClick={() => sync.mutate()} loading={sync.isPending}>{t('setup.switches.import')}</Button>
            {sync.isSuccess && <Text size="sm" c="up" role="status">{t('setup.switches.imported', { count: total })}</Text>}
          </Group>
          {sync.error && <Alert color="down" role="alert">{sync.error.message}</Alert>}
        </>
      ) : (
        <Text>{t('setup.switches.byHand')}</Text>
      )}
      <Text size="sm" c="dimmed">{t('setup.switches.place')}</Text>
      <StepButtons step="switches" onDone={onDone} />
    </Stack>
  )
}

function ThemeStep({ current, onDone }: { current?: string; onDone: () => void }) {
  const { t } = useTranslation()
  const [theme, setTheme] = useState(THEMES.includes(current as (typeof THEMES)[number]) ? current! : 'floorbit')
  const [name, setName] = useState('')
  const changes: Record<string, string> = { 'theme.preset': theme }
  if (name.trim()) changes['theme.name'] = name.trim()
  return (
    <Stack gap="sm" maw={520}>
      <TextInput label={t('setup.theme.name')} description={t('setup.theme.nameHelp')} value={name}
        onChange={(e) => setName(e.currentTarget.value)} maxLength={60} />
      <Radio.Group label={t('setup.theme.label')} value={theme} onChange={setTheme}>
        <Stack gap="xs" mt="xs">
          {THEMES.map((v) => <Radio key={v} value={v} label={t(`setup.theme.presets.${v}`)} />)}
        </Stack>
      </Radio.Group>
      <Text size="sm" c="dimmed">{t('setup.theme.custom')} <Anchor href="/settings">{t('common.settings')}</Anchor></Text>
      <StepButtons step="theme" onDone={onDone} onSave={() => put('/api/settings', changes)} />
    </Stack>
  )
}

function Finish() {
  const { t } = useTranslation()
  const done = useMutation({ mutationFn: () => post('/api/setup/finish'), onSuccess: () => window.location.assign('/') })
  return (
    <Stack gap="sm" maw={520}>
      <Text>{t('setup.finish.text')}</Text>
      <Text size="sm" c="dimmed">{t('setup.finish.later')}</Text>
      {done.error && <Alert color="down" role="alert">{done.error.message}</Alert>}
      <Group justify="flex-end">
        <Button onClick={() => done.mutate()} loading={done.isPending}>{t('setup.finish.open')}</Button>
      </Group>
    </Stack>
  )
}

/** First-run setup for a new install (issue #13): every step can be skipped and done later in Settings. */
export default function Setup() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const setup = useSetup()
  const data = setup.data
  // Opens at the first step not done or skipped yet; Back and the step headers move freely after that.
  const [picked, setPicked] = useState<number | null>(null)
  const first = data?.steps ? STEPS.findIndex((s) => !data.steps?.[s]) : 0
  const active = picked ?? (first === -1 ? STEPS.length : first)
  const next = () => {
    void client.invalidateQueries({ queryKey: qk.setup })
    setPicked(Math.min(active + 1, STEPS.length))
  }

  let body
  if (setup.isPending || !data) body = <Loader size="sm" />
  else if (data.needs_account) body = <AccountStep />
  else if (!data.can_set_up) body = <Alert color="gray">{data.done ? t('setup.alreadyDone') : t('setup.adminOnly')}</Alert>
  else {
    body = (
      <Stepper active={active} onStepClick={setPicked} allowNextStepsSelect={false} size="sm">
        <Stepper.Step label={t('setup.netbox.title')} description={t('setup.optional')}>
          <ConnectionStep service="netbox" connected={!!data.netbox} onDone={next} />
        </Stepper.Step>
        <Stepper.Step label={t('setup.librenms.title')} description={t('setup.optional')}>
          <ConnectionStep service="librenms" connected={!!data.librenms} onDone={next} />
        </Stepper.Step>
        <Stepper.Step label={t('setup.switches.title')}>
          <SwitchesStep setup={data} onDone={next} />
        </Stepper.Step>
        <Stepper.Step label={t('setup.theme.title')}>
          <ThemeStep current={data.theme} onDone={next} />
        </Stepper.Step>
        <Stepper.Completed>
          <Finish />
        </Stepper.Completed>
      </Stepper>
    )
  }

  return (
    <Layout title={t('setup.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('setup.title')} desc={data?.needs_account ? t('setup.introAccount') : t('setup.intro')} />
      {setup.error && <Alert color="down" role="alert" mb="md">{t('common.error', { message: setup.error.message })}</Alert>}
      {body}
    </Layout>
  )
}
