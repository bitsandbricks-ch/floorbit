import { Alert, Badge, Button, Code, Group, Loader, Paper, Stack, Text, Title } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconPlus } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useOidcProviders } from '@/api/queries'
import type { OidcProvider, OidcTestResult } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ProviderForm, type ProviderDraft } from './signin/ProviderForm'

/** Settings > Sign-in providers: OpenID Connect providers next to local accounts and Discord. Admins only. */
export default function SignIn() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const list = useOidcProviders()
  const [editing, setEditing] = useState<OidcProvider | null>(null)
  const [formOpen, form] = useDisclosure(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [tests, setTests] = useState<Record<string, OidcTestResult>>({})

  const save = useMutation({
    mutationFn: (d: ProviderDraft) => put(`/api/settings/oidc/${encodeURIComponent(d.id)}`, d),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.oidc })
      setMessage({ ok: true, text: t('signin.saved') })
      form.close()
    },
    onError: (e) => setFormError(e.message),
  })
  const remove = useMutation({
    mutationFn: (id: string) => del(`/api/settings/oidc/${encodeURIComponent(id)}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.oidc })
      setMessage({ ok: true, text: t('signin.removed') })
    },
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })
  const test = useMutation({
    mutationFn: (id: string) => post<OidcTestResult>(`/api/settings/oidc/${encodeURIComponent(id)}/test`, {}),
    onSuccess: (r, id) => setTests((x) => ({ ...x, [id]: r })),
    onError: (e, id) => setTests((x) => ({ ...x, [id]: { ok: false, error: e.message } })),
  })
  const roleLabel = (id: string) => list.data?.roles.find((r) => r.id === id)?.label ?? id

  return (
    <Layout title={t('signin.title')} back={{ href: '/settings', label: t('common.settings') }}>
      <PageHead title={t('signin.title')} desc={t('signin.intro')} />
      <Text size="sm" role="status" mb="sm" className={message ? (message.ok ? 'fb-tone-ok' : 'fb-tone-err') : undefined}>
        {message?.text}
      </Text>
      {list.error && (
        <Alert color="down" role="alert" mb="md">
          {t('common.error', { message: list.error.message })}
        </Alert>
      )}
      <Group justify="space-between" mt="lg" mb="xs">
        <Title order={2} size="h3">
          {t('signin.providers')}
        </Title>
        <Button leftSection={<IconPlus size={16} />} onClick={() => { setEditing(null); setFormError(null); form.open() }}>
          {t('signin.newProvider')}
        </Button>
      </Group>
      {list.isPending ? (
        <Loader size="sm" />
      ) : !list.data?.providers.length ? (
        <Text c="dimmed">{t('signin.none')}</Text>
      ) : (
        <Stack gap="sm">
          {list.data.providers.map((p) => {
            const result = tests[p.id]
            return (
              <Paper key={p.id} withBorder radius="lg" p="md">
                <Group justify="space-between" align="flex-start" wrap="wrap">
                  <Stack gap={4} style={{ minWidth: 0 }}>
                    <Group gap="xs">
                      <Text fw={600}>{t('signin.button', { name: p.name })}</Text>
                      {p.secret_set ? (
                        <Badge color="up" variant="light">{t('signin.ready')}</Badge>
                      ) : (
                        <Badge color="warn" variant="light">{t('signin.noSecret')}</Badge>
                      )}
                    </Group>
                    <Text size="sm" c="dimmed" style={{ wordBreak: 'break-all' }}>{p.issuer}</Text>
                    {!p.secret_set && (
                      <Text size="sm">
                        {t('signin.setSecret')} <Code>{p.secret_env}</Code>
                      </Text>
                    )}
                    <Text size="sm">
                      {p.role_mapping.length
                        ? t('signin.mappingSummary', {
                            claim: p.role_claim,
                            rules: p.role_mapping.map((r) => `${r.value} → ${roleLabel(r.role)}`).join(', '),
                          })
                        : t('signin.linkedOnly')}
                    </Text>
                    {result && (
                      <Text size="sm" role="status" className={result.ok ? 'fb-tone-ok' : 'fb-tone-err'}>
                        {result.ok ? t('signin.testOk', { keys: result.keys ?? 0 }) : (result.error ?? result.problems?.join(' '))}
                      </Text>
                    )}
                  </Stack>
                  <Group gap="xs">
                    <Button size="xs" variant="default" loading={test.isPending && test.variables === p.id} onClick={() => test.mutate(p.id)}>
                      {t('signin.test')}
                    </Button>
                    <Button size="xs" variant="default" onClick={() => { setEditing(p); setFormError(null); form.open() }}>
                      {t('signin.change')}
                    </Button>
                    <ConfirmButton size="xs" variant="subtle" danger label={t('signin.remove')}
                      question={t('signin.removeQuestion', { name: p.name })} onConfirm={() => remove.mutate(p.id)} />
                  </Group>
                </Group>
              </Paper>
            )
          })}
        </Stack>
      )}
      <Text size="sm" c="dimmed" mt="lg">{t('signin.fallback')}</Text>
      {list.data && formOpen && (
        <ProviderForm key={editing?.id ?? 'new'} provider={editing} list={list.data} opened={formOpen}
          busy={save.isPending} error={formError} onClose={form.close} onSave={(d) => save.mutate(d)} />
      )}
    </Layout>
  )
}
