import { ActionIcon, Alert, Anchor, Button, Code, Divider, Loader, PasswordInput, Select, Stack, Text, TextInput, Title } from '@mantine/core'
import { IconArmchair2, IconArrowRight, IconMoon, IconSun } from '@tabler/icons-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { type FormEvent, useEffect, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { ApiError, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { LoginOptions } from '@/api/types'
import { toggleScheme, useScheme } from '@/colorScheme'
import { Attribution } from '@/components/Attribution'
import { EventBrand } from '@/components/PublicPage'
import { LANGUAGES, type Lang, setLang } from '@/i18n'
import { readBoot } from '@/nav/boot'

const dbDown = (err: unknown) => err instanceof ApiError && err.data.code === 'database_unavailable'

// The hall on the left is a picture, not the event's plan: nothing about the real hall shows
// before sign-in. Five blocks of 2 x 16 seats, one traced to its switch in the highlight colour.
const BLOCKS = ['A', 'B', 'C', 'D', 'E']
const SEATS = 32
const TRACED = { block: 1, seat: 15 }
const WARN = { block: 3, seat: 9 }
function seatClass(block: number, seat: number) {
  if (block === TRACED.block && seat === TRACED.seat) return 'fb-hall-seat is-traced'
  if (block === WARN.block && seat === WARN.seat) return 'fb-hall-seat is-warn'
  return (seat * 37 + block * 61 + (seat % 5) * 11) % 100 < 62 ? 'fb-hall-seat is-in' : 'fb-hall-seat'
}

function HallArt() {
  return (
    <div className="fb-hall-art" aria-hidden="true">
      {BLOCKS.map((name, b) => {
        const traced = b === TRACED.block
        return (
          <div key={name} className="fb-hall-block">
            <span className="fb-hall-label">{name}</span>
            <div className="fb-hall-seats">
              {Array.from({ length: SEATS }, (_, s) => <i key={s} className={seatClass(b, s)} />)}
            </div>
            <div className="fb-hall-link">
              <span className={traced ? 'fb-hall-wire is-traced' : 'fb-hall-wire'} />
              <span className={traced ? 'fb-hall-switch is-traced' : 'fb-hall-switch'}>
                <span className="fb-hall-dot" />sw-{name.toLowerCase()}1
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** The sign-in page (issues #46, #1192), split in two: the event's brand and a hall on the left,
 *  and on the right the attendees' way to check in (while it is open) above the crew's sign-in.
 *  Phones get one column with a short strip of the hall on top. The form posts JSON; the plain
 *  form post on /login stays for scripts. */
export default function Login() {
  const { t, i18n } = useTranslation()
  const [params] = useSearchParams()
  const { brand } = readBoot()
  const scheme = useScheme()
  const toggle = toggleScheme()
  const options = useQuery({
    queryKey: [...qk.loginOptions, params.get('next') ?? ''],
    queryFn: () => get<LoginOptions>(`/api/auth/login-options?next=${encodeURIComponent(params.get('next') ?? '/')}`),
    staleTime: Infinity,
    // The database away (docs/database.md): say so at once and look again until it is back,
    // instead of retrying quietly behind a spinner.
    retry: (n, err) => !dbDown(err) && n < 3,
    refetchInterval: (q) => (dbDown(q.state.error) ? 10_000 : false),
  })
  const o = options.data
  const away = dbDown(options.error)
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
  const checkin = o?.checkin_url
  const title = checkin ? t('login.crewTitle') : t('login.title')
  useEffect(() => { document.title = `${t('login.title')} · Floorbit` }, [t])

  return (
    <main className="fb-signin">
      <section className="fb-signin-hall">
        <div className="fb-signin-brand"><EventBrand /></div>
        <HallArt />
        <div className="fb-signin-tagline">
          <p className="fb-signin-claim">{t('login.claim')}</p>
          <p className="fb-signin-sub">{brand.name ? t('login.claimEvent', { name: brand.name }) : t('login.claimSub')}</p>
        </div>
      </section>
      <section className="fb-signin-side">
        <div className="fb-signin-body">
          {checkin && (
            <div className="fb-signin-checkin">
              <div className="fb-signin-checkin-head">
                <IconArmchair2 size={24} stroke={1.8} aria-hidden="true" />
                <div>
                  <Title order={2} className="fb-signin-checkin-title">{t('login.checkinTitle')}</Title>
                  <Text size="sm" c="dimmed">{t('login.checkinText')}</Text>
                </div>
              </div>
              <Button component="a" href={checkin} size="md" fullWidth rightSection={<IconArrowRight size={18} />}>
                {t('login.checkin')}
              </Button>
              {o.checkin_address && (
                <Text size="xs" c="dimmed">{t('login.checkinAddress')} <Text span ff="var(--font-mono)" fw={600} c="var(--color-fg)">{o.checkin_address}</Text></Text>
              )}
            </div>
          )}
          <Stack gap="md">
            <div>
              <Title order={1} className="fb-signin-title" data-small={checkin ? true : undefined}>{title}</Title>
              <Text c="dimmed" size="sm" mt={4}>{t('login.intro')}</Text>
            </div>
            {options.isPending && <Loader aria-label={t('common.loading')} />}
            {options.error && (away
              ? <Alert color="warn" role="alert" title={t('database.downTitle')}>{t('database.downText')}</Alert>
              : <Alert color="down" role="alert">{t('common.error', { message: options.error.message })}</Alert>)}
            {error && <Alert color="down" role="alert">{error}</Alert>}
            {o?.no_users && (
              <Alert color="gray">
                <Trans i18nKey="login.noUsers"
                  components={{ setup: <Anchor href="/setup" />, code: <Code />, cmd: <Code>{'flask --app app users add <name>'}</Code> }} />
              </Alert>
            )}
            {/* With the database away the form stays in sight, greyed out, so the page keeps its
                shape and the fields are ready the moment it is back. */}
            {(o?.password_login || away) && (
              <form method="post" action="/login" onSubmit={submit}>
                <input type="hidden" name="next" value={o?.next ?? '/'} />
                <Stack gap="sm">
                  <TextInput label={t('login.username')} name="username" value={username} required autoComplete="username"
                    autoCapitalize="none" spellCheck={false} autoFocus={!username && !checkin} maxLength={64}
                    disabled={away} onChange={(e) => setUsername(e.currentTarget.value)} />
                  <PasswordInput label={t('login.password')} name="password" value={password} required
                    autoComplete="current-password" autoFocus={!!username} maxLength={256}
                    disabled={away} onChange={(e) => setPassword(e.currentTarget.value)} />
                  <Button type="submit" fullWidth size="md" variant={checkin ? 'default' : 'filled'} disabled={away}
                    loading={signIn.isPending || signIn.isSuccess}>{t('login.submit')}</Button>
                </Stack>
              </form>
            )}
            {o && o.providers.length > 0 && (
              <>
                {o.password_login && <Divider label={t('login.or')} />}
                <Stack gap="xs">
                  {o.providers.map((p) => (
                    <Button key={p.id} component="a" href={p.url} variant="default" size="md" fullWidth
                      className={`fb-login-provider fb-login-${p.id}`}>
                      {t('login.with', { name: p.label })}
                    </Button>
                  ))}
                </Stack>
              </>
            )}
          </Stack>
        </div>
        <footer className="fb-signin-foot">
          <div className="fb-signin-prefs">
            <Select size="xs" w={170} aria-label={t('login.language')} allowDeselect={false}
              data={LANGUAGES.map((l) => ({ value: l.code, label: l.label }))} value={i18n.language}
              onChange={(v) => { if (v) setLang(v as Lang) }} />
            {toggle && (
              <ActionIcon variant="default" size={30} onClick={toggle} data-theme-toggle
                aria-label={scheme === 'light' ? t('common.themeDark') : t('common.themeLight')}>
                {scheme === 'light' ? <IconMoon size={16} /> : <IconSun size={16} />}
              </ActionIcon>
            )}
          </div>
          <Attribution compact />
        </footer>
      </section>
    </main>
  )
}
