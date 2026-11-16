import { Alert, Anchor, Button, Code, Divider, Loader, Paper, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core'
import { IconArmchair2, IconArrowRight } from '@tabler/icons-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { LoginOptions } from '@/api/types'
import { PublicPage } from '@/components/PublicPage'

/** The sign-in page (issue #46), which is also where an attendee lands: so seat check-in comes
 *  first and big when it is open, and the crew's sign-in below it. The form posts JSON; the plain
 *  form post on /login stays for scripts. */
export default function Login() {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  const options = useQuery({
    queryKey: [...qk.loginOptions, params.get('next') ?? ''],
    queryFn: () => get<LoginOptions>(`/api/auth/login-options?next=${encodeURIComponent(params.get('next') ?? '/')}`),
    staleTime: Infinity,
  })
  const o = options.data
  // Until typed in, the name from the last failed try, so only the password needs typing again.
  const [typed, setUsername] = useState<string | null>(null)
  const username = typed ?? o?.username ?? ''
  const [password, setPassword] = useState('')
  const signIn = useMutation({
    mutationFn: () => post<{ ok: boolean; next: string }>('/api/auth/login', { username: username.trim(), password, next: o?.next ?? '/' }),
    onSuccess: (r) => window.location.assign(r.next),
    onError: () => setPassword(''),
  })
  const submit = (e: FormEvent) => { e.preventDefault(); signIn.mutate() }
  const error = signIn.error?.message ?? (signIn.isIdle ? o?.error : null)

  return (
    <PublicPage title={t('login.title')}>
      {o?.checkin_url && (
        <Paper withBorder radius="lg" p="lg" className="fb-public-hero">
          <Stack gap="sm">
            <IconArmchair2 size={32} stroke={1.6} color="var(--color-bit)" aria-hidden="true" />
            <div>
              <Title order={2} size="h3">{t('login.checkinTitle')}</Title>
              <Text size="sm" c="dimmed">{t('login.checkinText')}</Text>
            </div>
            <Button component="a" href={o.checkin_url} size="lg" fullWidth rightSection={<IconArrowRight size={18} />}>
              {t('login.checkin')}
            </Button>
          </Stack>
        </Paper>
      )}
      <Paper withBorder radius="lg" p="lg">
        <Stack gap="md">
          <div>
            <Title order={1} size={o?.checkin_url ? 'h3' : 'h2'}>{o?.checkin_url ? t('login.crewTitle') : t('login.title')}</Title>
            <Text c="dimmed" size="sm">{t('login.intro')}</Text>
          </div>
          {options.isPending && <Loader aria-label={t('common.loading')} />}
          {options.error && <Alert color="down" role="alert">{t('common.error', { message: options.error.message })}</Alert>}
          {error && <Alert color="down" role="alert">{error}</Alert>}
          {o?.no_users && (
            <Alert color="gray">
              <Trans i18nKey="login.noUsers"
                components={{ setup: <Anchor href="/setup" />, code: <Code />, cmd: <Code>{'flask --app app users add <name>'}</Code> }} />
            </Alert>
          )}
          {o?.password_login && (
            <form method="post" action="/login" onSubmit={submit}>
              <input type="hidden" name="next" value={o.next} />
              <Stack gap="sm">
                <TextInput label={t('login.username')} name="username" value={username} required autoComplete="username"
                  autoCapitalize="none" spellCheck={false} autoFocus={!username && !o.checkin_url} maxLength={64}
                  onChange={(e) => setUsername(e.currentTarget.value)} />
                <PasswordInput label={t('login.password')} name="password" value={password} required
                  autoComplete="current-password" autoFocus={!!username} maxLength={256}
                  onChange={(e) => setPassword(e.currentTarget.value)} />
                <Button type="submit" fullWidth variant={o.checkin_url ? 'default' : 'filled'}
                  loading={signIn.isPending || signIn.isSuccess}>{t('login.submit')}</Button>
              </Stack>
            </form>
          )}
          {o && o.providers.length > 0 && (
            <>
              {o.password_login && <Divider label={t('login.or')} />}
              <Stack gap="xs">
                {o.providers.map((p) => (
                  <Button key={p.id} component="a" href={p.url} variant="default" fullWidth
                    className={`fb-login-provider fb-login-${p.id}`}>
                    {t('login.with', { name: p.label })}
                  </Button>
                ))}
              </Stack>
            </>
          )}
        </Stack>
      </Paper>
    </PublicPage>
  )
}
