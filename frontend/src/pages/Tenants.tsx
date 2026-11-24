import { Alert, Anchor, Badge, Button, Code, CopyButton, Group, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { ErrorBanner, LoadingState, Panel } from '@/components/ui'
import { ConfirmButton } from '@bitsandbricks/ui'

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
    <Panel title={t('tenants.new')}>
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
    </Panel>
  )
}

type SetAdmin = { admin: string; password: string; made: boolean }

function Password({ value }: { value: string }) {
  const { t } = useTranslation()
  return (
    <Group gap="xs" wrap="nowrap">
      <Code style={{ overflowWrap: 'anywhere', minWidth: 0 }}>{value}</Code>
      <CopyButton value={value}>
        {({ copied, copy }) => (
          <Button size="compact-sm" variant="default" onClick={copy}>{copied ? t('tenants.copied') : t('tenants.copy')}</Button>
        )}
      </CopyButton>
    </Group>
  )
}

/** Adds a tenant's admin, or gives an existing account the Admin role and a new password: for a tenant locked out. */
function AdminForm({ tenant }: { tenant: Tenant }) {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const set = useMutation({
    mutationFn: () => post<SetAdmin>(`/api/platform/tenants/${tenant.id}/admin`, { username: username.trim() }),
    onSuccess: () => setUsername(''),
  })
  return (
    <Stack gap="xs">
      <Group align="flex-end" gap="xs">
        <TextInput label={t('tenants.setAdminName')} description={t('tenants.setAdminHelp')} maxLength={32}
          autoCapitalize="none" spellCheck={false} autoComplete="off" style={{ flex: 1, minWidth: 200 }}
          value={username} onChange={(e) => setUsername(e.currentTarget.value)} />
        <Button loading={set.isPending} disabled={!username.trim()} onClick={() => set.mutate()}>{t('tenants.setAdminButton')}</Button>
      </Group>
      {set.error && <Text size="sm" c="down" role="alert">{set.error.message}</Text>}
      {set.data && (
        <Alert color="up" role="status">
          <Stack gap="xs">
            <Text size="sm">{t(set.data.made ? 'tenants.adminMade' : 'tenants.adminReset', { admin: set.data.admin })}</Text>
            <Password value={set.data.password} />
          </Stack>
        </Alert>
      )}
    </Stack>
  )
}

function Row({ tenant, here, onChanged }: { tenant: Tenant; here: string; onChanged: () => void }) {
  const { t } = useTranslation()
  const change = useMutation({
    mutationFn: (status: Tenant['status']) => patch(`/api/platform/tenants/${tenant.id}`, { status }),
    onSuccess: onChanged,
  })
  const suspended = tenant.status === 'suspended'
  const [adminOpen, setAdminOpen] = useState(false)
  return (
    <Stack gap="xs">
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
        {tenant.id !== DEFAULT && (
          <Group gap="xs">
            <Button size="compact-sm" variant="default" onClick={() => setAdminOpen((o) => !o)} aria-expanded={adminOpen}>
              {t('tenants.setAdmin')}
            </Button>
            {suspended ? (
              <Button size="compact-sm" variant="default" loading={change.isPending} onClick={() => change.mutate('active')}>
                {t('tenants.resume')}
              </Button>
            ) : (
              <ConfirmButton size="compact-sm" variant="default" danger label={t('tenants.suspend')}
                question={t('tenants.suspendQuestion', { name: tenant.name || tenant.id })} onConfirm={() => change.mutate('suspended')} />
            )}
          </Group>
        )}
      </Group>
      {adminOpen && <AdminForm tenant={tenant} />}
    </Stack>
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
                  <Password value={made.password} />
                </>
              )}
            </Stack>
          </Alert>
        )}
        {query.isPending ? <LoadingState /> : d && (
          <>
            <Panel title={t('tenants.list', { count: d.tenants.length })}>
              <Stack gap="sm">
                {d.tenants.map((tn) => <Row key={tn.id} tenant={tn} here={d.here} onChanged={refresh} />)}
              </Stack>
            </Panel>
            <NewTenant onMade={(m) => { setMade(m); refresh() }} />
            <Text size="sm" c="dimmed">{t('tenants.docs')}</Text>
          </>
        )}
      </Stack>
    </Layout>
  )
}
