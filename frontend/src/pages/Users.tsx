import { Alert, Badge, Button, Group, MultiSelect, PasswordInput, Select, SimpleGrid, Stack, Switch, Text, TextInput } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, patch, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import type { Account, AccountsList } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { ErrorBanner, Panel } from '@/components/ui'
import { ConfirmButton } from '@/components/ConfirmButton'

const CREW_ROLES = ['admin', 'lead', 'tech']

type Open = 'password' | 'discord' | 'sign-in' | 'dashboards' | null

const path = (username: string) => `/api/users/${encodeURIComponent(username)}`

/** One account: its role, and the password reset and sign-in links behind buttons. */
function AccountRow({ user, list, boards, onSaved }: {
  user: Account; list: AccountsList; boards: { id: string; name: string }[]; onSaved: (l: AccountsList) => void
}) {
  const { t } = useTranslation()
  const isMe = user.username === list.me
  const [open, setOpen] = useState<Open>(null)
  const [done, setDone] = useState('')
  const [password, setPassword] = useState('')
  const [discordId, setDiscordId] = useState(user.discord_id)
  const [provider, setProvider] = useState<string | null>(list.oidc[0]?.id ?? null)
  const [subject, setSubject] = useState('')
  const [limit, setLimit] = useState<string[]>(user.dashboards ?? [])
  const change = useMutation({
    mutationFn: (body: Record<string, unknown>) => patch<AccountsList>(path(user.username), body),
    onSuccess: (l, body) => {
      if (body.password && isMe) { window.location.assign('/login'); return }   // signed out everywhere
      onSaved(l)
      setOpen(null)
      setPassword('')
      setSubject('')
      setDone(body.password ? t('users.passwordChanged') : '')
    },
  })
  const remove = useMutation({ mutationFn: () => del<AccountsList>(path(user.username)), onSuccess: onSaved })
  const label = (id: string) => list.oidc.find((p) => p.id === id)?.label ?? id
  const linked = user.identities.map((id) => (id === 'discord' ? `Discord ${user.discord_id}` : label(id)))
  const toggle = (what: Open) => { change.reset(); setDone(''); setOpen(open === what ? null : what) }
  let form: ReactNode = null
  if (open === 'password') {
    form = (
      <Group align="flex-end" gap="xs">
        <PasswordInput label={t('users.newPassword')} placeholder={t('users.passwordHint')} autoComplete="new-password"
          style={{ flex: 1, minWidth: 200 }} value={password} onChange={(e) => setPassword(e.currentTarget.value)} />
        <Button loading={change.isPending} disabled={password.length < 8} onClick={() => change.mutate({ password })}>
          {t('users.save')}
        </Button>
      </Group>
    )
  } else if (open === 'discord') {
    form = (
      <Group align="flex-end" gap="xs">
        <TextInput label={t('users.discordId')} placeholder={t('users.discordHint')} inputMode="numeric" autoComplete="off"
          style={{ flex: 1, minWidth: 200 }} value={discordId} onChange={(e) => setDiscordId(e.currentTarget.value)} />
        <Button loading={change.isPending} onClick={() => change.mutate({ discord_id: discordId.trim() })}>{t('users.save')}</Button>
      </Group>
    )
  } else if (open === 'dashboards') {
    form = (
      <Group align="flex-end" gap="xs">
        <MultiSelect label={t('users.dashboards')} description={t('users.dashboardsHelp')} placeholder={limit.length ? undefined : t('users.allDashboards')}
          data={boards.map((b) => ({ value: b.id, label: b.name }))} value={limit} onChange={setLimit} clearable searchable
          maxValues={20} style={{ flex: 1, minWidth: 220 }} />
        <Button loading={change.isPending} onClick={() => change.mutate({ dashboards: limit })}>{t('users.save')}</Button>
      </Group>
    )
  } else if (open === 'sign-in') {
    form = (
      <Group align="flex-end" gap="xs">
        <Select label={t('users.provider')} data={list.oidc.map((p) => ({ value: p.id, label: p.label }))} value={provider}
          onChange={setProvider} allowDeselect={false} w={{ base: '100%', sm: 200 }} />
        <TextInput label={t('users.subject')} placeholder={t('users.subjectHint')} maxLength={255} autoComplete="off"
          style={{ flex: 1, minWidth: 200 }} value={subject} onChange={(e) => setSubject(e.currentTarget.value)} />
        <Button loading={change.isPending} disabled={!provider}
          onClick={() => change.mutate({ identity: { provider, subject: subject.trim() } })}>{t('users.save')}</Button>
      </Group>
    )
  }
  const error = change.error ?? remove.error

  return (
    <Stack gap="xs" py="sm" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }}>
      <Group justify="space-between" align="flex-start" gap="sm">
        <div style={{ minWidth: 0, flex: 1 }}>
          <Group gap={6}>
            <Text fw={600}>{user.display_name}</Text>
            {isMe && <Badge size="sm" variant="light">{t('users.you')}</Badge>}
            {user.platform_admin && <Badge size="sm" variant="light" color="trace" tt="none">{t('users.platformAdmin')}</Badge>}
          </Group>
          <Text size="xs" c="dimmed" style={{ overflowWrap: 'anywhere' }}>
            {user.username}
            {linked.length ? ` · ${t('users.linked', { list: linked.join(', ') })}` : ''}
            {user.created_by === 'platform' ? ` · ${t('users.byPlatform')}`
              : user.created_by ? ` · ${t('users.joinedWith', { via: user.created_by === 'discord' ? 'Discord' : label(user.created_by) })}` : ''}
          </Text>
        </div>
        <Select aria-label={t('users.role')} w={{ base: '100%', xs: 170 }} allowDeselect={false} disabled={isMe}
          title={isMe ? t('users.ownRole') : undefined} value={user.role}
          data={list.roles.map((r) => ({ value: r.id, label: r.label }))}
          onChange={(role) => role && role !== user.role && change.mutate({ role })} />
      </Group>
      <Group gap="xs">
        <Button size="compact-sm" variant="default" onClick={() => toggle('password')}>{t('users.resetPassword')}</Button>
        {(list.discord || user.discord_id) && (
          <Button size="compact-sm" variant="default" onClick={() => toggle('discord')}>
            {user.discord_id ? 'Discord' : t('users.linkDiscord')}
          </Button>
        )}
        {list.oidc.length > 0 && (
          <Button size="compact-sm" variant="default" onClick={() => toggle('sign-in')}>{t('users.linkSignIn')}</Button>
        )}
        {/* Only for screens (kiosk, viewer or a custom role): the crew's own accounts aren't limited. */}
        {boards.length > 0 && (user.dashboards?.length || !CREW_ROLES.includes(user.role)) && (
          <Button size="compact-sm" variant="default" onClick={() => toggle('dashboards')}>
            {user.dashboards?.length ? t('users.onlyDashboards', { count: user.dashboards.length }) : t('users.limitDashboards')}
          </Button>
        )}
        {list.platform && (user.platform_admin ? (
          <ConfirmButton size="compact-sm" variant="default" danger label={t('users.takePlatform')}
            question={t('users.takePlatformQuestion', { name: user.display_name })}
            loading={change.isPending} onConfirm={() => change.mutate({ platform_admin: false })} />
        ) : user.role === 'admin' && (
          <ConfirmButton size="compact-sm" variant="default" danger label={t('users.makePlatform')}
            question={t('users.makePlatformQuestion', { name: user.display_name })}
            loading={change.isPending} onConfirm={() => change.mutate({ platform_admin: true })} />
        ))}
        <ConfirmButton size="compact-sm" variant="light" danger label={t('users.remove')} disabled={isMe}
          title={isMe ? t('users.ownAccount') : undefined} question={t('users.removeQuestion', { name: user.display_name })}
          loading={remove.isPending} onConfirm={() => remove.mutate()} />
      </Group>
      {form}
      {error && <Text size="sm" c="down" role="alert">{error.message}</Text>}
      {done && <Text size="sm" c="up" role="status">{done}</Text>}
    </Stack>
  )
}

function AddAccount({ list, onSaved }: { list: AccountsList; onSaved: (l: AccountsList) => void }) {
  const { t } = useTranslation()
  const empty = { username: '', display_name: '', password: '', role: 'lead' }
  const [form, setForm] = useState(empty)
  const [added, setAdded] = useState('')
  const add = useMutation({
    mutationFn: () => post<AccountsList>('/api/users', form),
    onSuccess: (l) => { onSaved(l); setAdded(form.username); setForm(empty) },
  })
  const set = (k: keyof typeof empty) => (v: string) => { setAdded(''); setForm((f) => ({ ...f, [k]: v })) }
  return (
    <Panel title={t('users.add')}>
      <form onSubmit={(e) => { e.preventDefault(); add.mutate() }} autoComplete="off">
        <Stack gap="sm">
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            <TextInput label={t('users.username')} placeholder={t('users.usernameHint')} required maxLength={32}
              autoCapitalize="none" spellCheck={false} value={form.username}
              onChange={(e) => set('username')(e.currentTarget.value)} />
            <TextInput label={t('users.displayName')} placeholder={t('users.optional')} maxLength={64}
              value={form.display_name} onChange={(e) => set('display_name')(e.currentTarget.value)} />
            <PasswordInput label={t('users.password')} placeholder={t('users.passwordHint')} required minLength={8}
              autoComplete="new-password" value={form.password}
              onChange={(e) => set('password')(e.currentTarget.value)} />
            <Select label={t('users.role')} allowDeselect={false} value={form.role}
              data={list.roles.map((r) => ({ value: r.id, label: r.label }))} onChange={(v) => v && set('role')(v)} />
          </SimpleGrid>
          {add.error && <Alert color="down" role="alert">{add.error.message}</Alert>}
          {added && <Text size="sm" c="up" role="status">{t('users.added', { name: added })}</Text>}
          <Group justify="flex-end">
            <Button type="submit" loading={add.isPending}>{t('users.addButton')}</Button>
          </Group>
        </Stack>
      </form>
    </Panel>
  )
}

type Access = { visits: boolean; shown: boolean }

/** On a tenant other than the default one: whether the platform's admins may come in. */
function PlatformVisits() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.platformAccess, queryFn: () => get<Access>('/api/tenant/platform-access') })
  const save = useMutation({
    mutationFn: (visits: boolean) => put<Access>('/api/tenant/platform-access', { visits }),
    onSuccess: (a) => qc.setQueryData(qk.platformAccess, a),
  })
  if (!query.data?.shown) return null
  return (
    <Panel title={t('users.platformVisits')}>
      <Switch checked={query.data.visits} disabled={save.isPending} label={t('users.platformVisitsLabel')}
        description={t('users.platformVisitsHelp')} onChange={(e) => save.mutate(e.currentTarget.checked)} />
      {save.error && <Text size="sm" c="down" role="alert" mt="xs">{save.error.message}</Text>}
    </Panel>
  )
}

/** Settings > Users: accounts, their roles and sign-in links. Admins only (the server checks). */
export default function Users() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.users, queryFn: () => get<AccountsList>('/api/users') })
  const saved = (l: AccountsList) => qc.setQueryData(qk.users, l)
  const list = query.data
  // Only to name them in the dashboard limit; a page that can't read them just leaves that out.
  const boards = useQuery({ queryKey: qk.boards, queryFn: () => get<{ layouts: { id: string; name: string }[] }>('/api/dashboards') })

  return (
    <Layout title={t('users.title')} back={{ href: '/settings', label: t('users.settings') }}>
      <PageHead title={t('users.title')} desc={t('users.intro')}
        actions={<Button component="a" href="/settings/teams" variant="default">{t('users.rolesAndTeams')}</Button>} />
      <Stack gap="md">
        <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
        {list && (
          <>
            <Text size="sm" c="dimmed">
              {list.roles.map((r, i) => (
                <span key={r.id}>{i ? ' ' : ''}<strong>{r.label}:</strong> {t(`teams.roleText.${r.id}`, { defaultValue: r.description })}</span>
              ))}
            </Text>
            <Panel title={t('users.accounts')} desc={t('users.accountsHelp')}>
              <div aria-live="polite">
                {list.users.map((u) => <AccountRow key={u.username} user={u} list={list} boards={boards.data?.layouts ?? []} onSaved={saved} />)}
              </div>
            </Panel>
            <AddAccount list={list} onSaved={saved} />
            <PlatformVisits />
          </>
        )}
      </Stack>
    </Layout>
  )
}
