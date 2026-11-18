import { Alert, Anchor, Badge, Button, Code, CopyButton, Group, Paper, SimpleGrid, Stack, Text, TextInput, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ErrorBanner, LoadingState } from '@/components/ui'

type Tenant = { id: string; name: string; url: string; status: 'active' | 'suspended' }
type Answer = { tenants: Tenant[]; here: string }
type Made = { tenant: Tenant; admin: string | null; password: string | null }

const DEFAULT = 'default'

function NewTenant({ onMade }: { onMade: (m: Made) => void }) {
  const { t } = useTranslation()
  const [id, setId] = useState('')
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [admin, setAdmin] = useState('')
  const make = useMutation({
    mutationFn: () => post<Made>('/api/platform/tenants', { id: id.trim(), name: name.trim(), url: url.trim(), admin: admin.trim() }),
    onSuccess: (m) => { setId(''); setName(''); setUrl(''); setAdmin(''); onMade(m) },
  })
  return (
    <Paper withBorder radius="lg" p="md">
      <Title order={2} size="h4" mb="xs">{t('tenants.new')}</Title>
      <Stack gap="sm">
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label={t('tenants.id')} description={t('tenants.idHelp')} value={id} maxLength={40} required
            onChange={(e) => setId(e.currentTarget.value.toLowerCase())} />
          <TextInput label={t('tenants.name')} description={t('tenants.nameHelp')} value={name} maxLength={80}
            onChange={(e) => setName(e.currentTarget.value)} />
          <TextInput label={t('tenants.url')} description={t('tenants.urlHelp')} value={url} placeholder="https://tenant.example.com"
            onChange={(e) => setUrl(e.currentTarget.value)} />
          <TextInput label={t('tenants.admin')} description={t('tenants.adminHelp')} value={admin} maxLength={40}
            onChange={(e) => setAdmin(e.currentTarget.value)} />
        </SimpleGrid>
        {make.error && <Alert color="down" role="alert">{make.error.message}</Alert>}
        <Group justify="flex-end">
          <Button loading={make.isPending} disabled={!id.trim()} onClick={() => make.mutate()}>{t('tenants.add')}</Button>
        </Group>
      </Stack>
    </Paper>
  )
}

function Row({ tenant, here, onChanged }: { tenant: Tenant; here: string; onChanged: () => void }) {
  const { t } = useTranslation()
  const change = useMutation({
    mutationFn: (status: Tenant['status']) => patch(`/api/platform/tenants/${tenant.id}`, { status }),
    onSuccess: onChanged,
  })
  const suspended = tenant.status === 'suspended'
  return (
    <Group justify="space-between" wrap="wrap" gap="xs">
      <Stack gap={0} style={{ minWidth: 0 }}>
        <Group gap={6}>
          <Text fw={600} style={{ overflowWrap: 'anywhere' }}>{tenant.name || tenant.id}</Text>
          <Code>{tenant.id}</Code>
          {tenant.id === here && <Badge variant="light" color="trace" tt="none">{t('tenants.here')}</Badge>}
          {suspended
            ? <Badge variant="light" color="down" tt="none">{t('tenants.suspended')}</Badge>
            : <Badge variant="light" color="up" tt="none">{t('tenants.active')}</Badge>}
        </Group>
        <Text size="xs" c="dimmed">
          {tenant.id === DEFAULT ? t('tenants.defaultHelp') : (
            tenant.url ? <Anchor href={tenant.url} size="xs" target="_blank" rel="noreferrer">{tenant.url}</Anchor> : t('tenants.noUrl')
          )}
        </Text>
        {change.error && <Text size="xs" c="down" role="alert">{change.error.message}</Text>}
      </Stack>
      {tenant.id !== DEFAULT && (suspended ? (
        <Button size="compact-sm" variant="default" loading={change.isPending} onClick={() => change.mutate('active')}>
          {t('tenants.resume')}
        </Button>
      ) : (
        <ConfirmButton size="compact-sm" variant="default" danger label={t('tenants.suspend')}
          question={t('tenants.suspendQuestion', { name: tenant.name || tenant.id })} onConfirm={() => change.mutate('suspended')} />
      ))}
    </Group>
  )
}

/** The platform's tenants: one per club or organisation, each with its own accounts, data, look and agents. */
export default function Tenants() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.tenants, queryFn: () => get<Answer>('/api/platform/tenants') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.tenants })
  const [made, setMade] = useState<Made | null>(null)
  const d = query.data

  return (
    <Layout title={t('tenants.title')} back={{ href: '/settings', label: t('tenants.settings') }}>
      <PageHead title={t('tenants.title')} desc={t('tenants.intro')} />
      <Stack gap="md">
        <ErrorBanner error={query.error} />
        {made && (
          <Alert color="up" role="status" withCloseButton onClose={() => setMade(null)}
            title={t('tenants.madeTitle', { name: made.tenant.name || made.tenant.id })}>
            <Stack gap="xs">
              <Text size="sm">{t('tenants.madeHelp', { id: made.tenant.id })}</Text>
              <Code block>{`FLOORBIT_TENANT=${made.tenant.id}`}</Code>
              {made.admin && made.password && (
                <>
                  <Text size="sm">{t('tenants.madeAdmin', { admin: made.admin })}</Text>
                  <Group gap="xs" wrap="nowrap">
                    <Code style={{ overflowWrap: 'anywhere', minWidth: 0 }}>{made.password}</Code>
                    <CopyButton value={made.password}>
                      {({ copied, copy }) => (
                        <Button size="compact-sm" variant="default" onClick={copy}>{copied ? t('tenants.copied') : t('tenants.copy')}</Button>
                      )}
                    </CopyButton>
                  </Group>
                </>
              )}
            </Stack>
          </Alert>
        )}
        {query.isPending ? <LoadingState /> : d && (
          <>
            <Paper withBorder radius="lg" p="md">
              <Title order={2} size="h4" mb="xs">{t('tenants.list', { count: d.tenants.length })}</Title>
              <Stack gap="sm">
                {d.tenants.map((tn) => <Row key={tn.id} tenant={tn} here={d.here} onChanged={refresh} />)}
              </Stack>
            </Paper>
            <NewTenant onMade={(m) => { setMade(m); refresh() }} />
            <Text size="sm" c="dimmed">{t('tenants.docs')}</Text>
          </>
        )}
      </Stack>
    </Layout>
  )
}
