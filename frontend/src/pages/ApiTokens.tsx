import {
  Alert, Badge, Button, Checkbox, Code, CopyButton, Group, Loader, NumberInput, Paper, Select, Stack, Text, TextInput, Title,
} from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useRoles } from '@/api/queries'
import type { ApiToken } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

type Answer = { tokens: ApiToken[]; max_days: number }
type Made = { token: ApiToken; secret: string }

function NewToken({ maxDays, onMade }: { maxDays: number; onMade: (m: Made) => void }) {
  const { t } = useTranslation()
  const roles = useRoles()
  const [name, setName] = useState('')
  const [role, setRole] = useState<string | null>('viewer')
  const [readOnly, setReadOnly] = useState(true)
  const [days, setDays] = useState<number | string>(90)
  const make = useMutation({
    mutationFn: () => post<Made>('/api/settings/api-tokens', {
      name: name.trim(), role, read_only: readOnly, expires_days: days === '' ? null : Number(days),
    }),
    onSuccess: (m) => { setName(''); onMade(m) },
  })
  const options = (roles.data?.roles ?? []).map((r) => ({ value: r.id, label: r.label }))
  return (
    <Paper withBorder radius="lg" p="md">
      <Title order={2} size="h4" mb="xs">{t('api.new')}</Title>
      <Stack gap="sm">
        <TextInput label={t('api.name')} description={t('api.nameHelp')} value={name} maxLength={60}
          onChange={(e) => setName(e.currentTarget.value)} />
        <Group grow align="flex-start">
          <Select label={t('api.role')} description={t('api.roleHelp')} data={options} value={role} onChange={setRole}
            allowDeselect={false} />
          <NumberInput label={t('api.expires')} description={t('api.expiresHelp')} min={1} max={maxDays}
            value={days} onChange={setDays} />
        </Group>
        <Checkbox label={t('api.readOnly')} description={t('api.readOnlyHelp')} checked={readOnly}
          onChange={(e) => setReadOnly(e.currentTarget.checked)} />
        {make.error && <Alert color="down" role="alert">{make.error.message}</Alert>}
        <Group justify="flex-end">
          <Button loading={make.isPending} disabled={!name.trim() || !role} onClick={() => make.mutate()}>{t('api.make')}</Button>
        </Group>
      </Stack>
    </Paper>
  )
}

/** Tokens for scripts and other tools, each with a role, maybe read-only, maybe expiring. */
export default function ApiTokens() {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.apiTokens, queryFn: () => get<Answer>('/api/settings/api-tokens') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.apiTokens })
  const [made, setMade] = useState<Made | null>(null)
  const revoke = useMutation({ mutationFn: (id: string) => del(`/api/settings/api-tokens/${id}`), onSuccess: refresh })
  const date = (ts: number | null) => (ts ? new Date(ts * 1000).toLocaleDateString(i18n.language) : '')
  const d = query.data
  const error = query.error ?? revoke.error

  return (
    <Layout title={t('api.title')} back={{ href: '/settings', label: t('api.settings') }}>
      <PageHead title={t('api.title')} desc={t('api.intro')} />
      <Stack gap="md">
        {error && <Alert color="down" role="alert">{t('common.error', { message: error.message })}</Alert>}
        {made && (
          <Alert color="up" role="status" withCloseButton onClose={() => setMade(null)} title={t('api.madeTitle', { name: made.token.name })}>
            <Stack gap="xs">
              <Text size="sm">{t('api.madeHelp')}</Text>
              <Group gap="xs" wrap="nowrap">
                <Code style={{ overflowWrap: 'anywhere', minWidth: 0 }}>{made.secret}</Code>
                <CopyButton value={made.secret}>
                  {({ copied, copy }) => (
                    <Button size="compact-sm" variant="default" onClick={copy}>{copied ? t('api.copied') : t('api.copy')}</Button>
                  )}
                </CopyButton>
              </Group>
            </Stack>
          </Alert>
        )}
        {query.isPending ? <Loader aria-label={t('common.loading')} /> : d && (
          <>
            <Paper withBorder radius="lg" p="md">
              <Title order={2} size="h4" mb="xs">{t('api.tokens')}</Title>
              {d.tokens.length === 0 ? <Text size="sm" c="dimmed">{t('api.none')}</Text> : (
                <Stack gap="sm">
                  {d.tokens.map((tk) => (
                    <Group key={tk.id} justify="space-between" wrap="wrap" gap="xs">
                      <Stack gap={0} style={{ minWidth: 0 }}>
                        <Group gap={6}>
                          <Text fw={600} style={{ overflowWrap: 'anywhere' }}>{tk.name}</Text>
                          <Badge variant="light" color="trace" tt="none">{tk.role_label}</Badge>
                          {tk.read_only && <Badge variant="light" color="gray" tt="none">{t('api.readOnlyBadge')}</Badge>}
                          {tk.expired && <Badge variant="light" color="down" tt="none">{t('api.expired')}</Badge>}
                        </Group>
                        <Text size="xs" c="dimmed">
                          {t('api.made', { date: date(tk.created_at), who: tk.created_by ?? '?' })}
                          {' · '}{tk.expires_at ? t('api.until', { date: date(tk.expires_at) }) : t('api.noExpiry')}
                          {' · '}{tk.last_used_at ? t('api.used', { date: date(tk.last_used_at) }) : t('api.neverUsed')}
                        </Text>
                      </Stack>
                      <ConfirmButton size="compact-sm" variant="default" danger label={t('api.revoke')}
                        question={t('api.revokeQuestion', { name: tk.name })} onConfirm={() => revoke.mutate(tk.id)} />
                    </Group>
                  ))}
                </Stack>
              )}
            </Paper>
            <NewToken maxDays={d.max_days} onMade={(m) => { setMade(m); refresh() }} />
            <Text size="sm" c="dimmed">{t('api.docs')}</Text>
          </>
        )}
      </Stack>
    </Layout>
  )
}
