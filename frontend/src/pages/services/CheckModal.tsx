import { Alert, Button, Group, Modal, NumberInput, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { CHECK_KINDS, UDP_ASKS } from '@/api/serviceChecks'
import type { CheckKind, OwnCheck, OwnCheckResult, UdpAsk } from '@/api/serviceChecks'
import { ConfirmButton } from '@bitsandbricks/ui'
import { useAgentChoices } from '@/components/agentChoices'

const SLOW: Record<CheckKind, number> = { ping: 100, tcp: 200, udp: 200, http: 1000 }

/** Add or change an own check (issue #1338): a ping, a TCP port, a UDP port or an HTTP(S) address,
 *  run by the local agent. "Test" runs it once before it is saved. */
export function CheckModal({ check, onClose }: { check: OwnCheck | null; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    name: check?.name ?? '', kind: check?.kind ?? 'ping' as CheckKind, host: check?.host ?? '',
    port: check?.port ?? '' as number | '', ask: (check?.ask || 'none') as UdpAsk, url: check?.url ?? '',
    expect: check?.expect || '200-399', contains: check?.contains ?? '',
    cert_warn_days: check?.cert_warn_days ?? 14, slow_ms: check?.slow_ms ?? SLOW[check?.kind ?? 'ping'],
    from: check?.from ?? '',
  })
  const agents = useAgentChoices()
  const [slowTouched, setSlowTouched] = useState(!!check)
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }))
  const body = () => {
    const common = { name: form.name, kind: form.kind, slow_ms: form.slow_ms, from: form.from }
    if (form.kind === 'http') return { ...common, url: form.url.trim(), expect: form.expect, contains: form.contains, cert_warn_days: form.cert_warn_days }
    return { ...common, host: form.host.trim(), ...(form.kind !== 'ping' && { port: form.port === '' ? null : form.port }),
      ...(form.kind === 'udp' && { ask: form.ask }) }
  }
  const done = () => { void qc.invalidateQueries({ queryKey: qk.services }); onClose() }
  const save = useMutation({ mutationFn: () => (check ? put(`/api/services/checks/${check.id}`, body()) : post('/api/services/checks', body())), onSuccess: done })
  const remove = useMutation({ mutationFn: () => del(`/api/services/checks/${check!.id}`), onSuccess: done })
  const test = useMutation({ mutationFn: () => post<OwnCheckResult>('/api/services/checks/test', body()) })
  const error = save.error ?? remove.error
  const ready = !!form.name.trim() && (form.kind === 'http' ? !!form.url.trim() : !!form.host.trim() && (form.kind === 'ping' || form.port !== ''))
  return (
    <Modal opened onClose={onClose} size="lg" title={check ? t('services.check.edit') : t('services.check.add')}>
      <Stack gap="sm">
        <TextInput label={t('services.name')} placeholder={t('services.check.namePlaceholder')} value={form.name} onChange={(e) => set({ name: e.currentTarget.value })} />
        <div>
          <Text size="sm" fw={500} mb={4} id="check-kind">{t('services.check.kind')}</Text>
          <SegmentedControl fullWidth aria-labelledby="check-kind" value={form.kind}
            onChange={(v) => { const kind = v as CheckKind; set({ kind, ...(!slowTouched && { slow_ms: SLOW[kind] }) }); test.reset() }}
            data={CHECK_KINDS.map((k) => ({ value: k, label: t(`services.check.kinds.${k}`) }))} />
        </div>
        {form.kind === 'http' ? (
          <>
            <TextInput label={t('services.check.url')} description={t('services.check.urlHelp')} placeholder="https://www.example.com/health"
              value={form.url} onChange={(e) => set({ url: e.currentTarget.value })} />
            <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
              <TextInput label={t('services.check.expect')} description={t('services.check.expectHelp')} value={form.expect} onChange={(e) => set({ expect: e.currentTarget.value })} />
              <TextInput label={t('services.check.contains')} description={t('services.check.containsHelp')} value={form.contains} onChange={(e) => set({ contains: e.currentTarget.value })} />
            </SimpleGrid>
            {form.url.trim().toLowerCase().startsWith('https:') && (
              <NumberInput label={t('services.check.certWarn')} min={0} max={365} value={form.cert_warn_days}
                onChange={(v) => set({ cert_warn_days: typeof v === 'number' ? v : 0 })} />
            )}
          </>
        ) : (
          <SimpleGrid cols={{ base: 1, xs: form.kind === 'ping' ? 1 : 2 }} spacing="sm">
            <TextInput label={t('services.check.host')} description={t('services.check.hostHelp')} placeholder="192.0.2.40"
              value={form.host} onChange={(e) => set({ host: e.currentTarget.value })} />
            {form.kind !== 'ping' && (
              <NumberInput label={t('services.port')} min={1} max={65535} allowDecimal={false} value={form.port}
                onChange={(v) => set({ port: typeof v === 'number' ? v : '' })} />
            )}
          </SimpleGrid>
        )}
        {form.kind === 'udp' && (
          <Select label={t('services.check.ask')} description={t('services.check.askHelp')} allowDeselect={false} value={form.ask}
            onChange={(v) => set({ ask: (v ?? 'none') as UdpAsk })} data={UDP_ASKS.map((a) => ({ value: a, label: t(`services.check.asks.${a}`) }))} />
        )}
        <NumberInput label={t('services.check.slow')} suffix=" ms" min={1} max={60000} allowDecimal={false} value={form.slow_ms}
          onChange={(v) => { setSlowTouched(true); set({ slow_ms: typeof v === 'number' ? v : 1 }) }} />
        <Select label={t('services.check.from')} description={t('services.check.fromHelp')} clearable searchable
          placeholder={t('services.check.fromAny')} data={agents.data} value={form.from || null}
          onChange={(v) => { set({ from: v ?? '' }); test.reset() }} />
        <Group gap="sm" wrap="nowrap" align="center" className="fb-check-test">
          <Button variant="default" size="compact-md" disabled={!ready} loading={test.isPending} onClick={() => test.mutate()}>{t('services.check.test')}</Button>
          <Text size="sm" role="status" c={test.data ? (test.data.status === 'down' ? 'down' : test.data.status === 'warn' ? 'warn' : undefined) : 'dimmed'}>
            {test.error ? test.error.message : test.data ? testLine(t, test.data) : t('services.check.testHelp')}
          </Text>
        </Group>
        {error && <Alert color="down" role="alert">{error.message}</Alert>}
        <Group justify={check ? 'space-between' : 'flex-end'}>
          {check && <ConfirmButton variant="subtle" danger label={t('services.remove')} question={t('services.removeQuestion', { name: check.name })} onConfirm={() => remove.mutate()} />}
          <Button loading={save.isPending} disabled={!ready} onClick={() => save.mutate()}>{t('services.save')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}

type T = (key: string, opts?: Record<string, unknown>) => string

function testLine(t: T, r: OwnCheckResult): string {
  const parts = [t(`services.status.${r.status}`)]
  if (r.code != null) parts.push(t('services.check.code', { code: r.code }))
  if (r.latency_ms != null) parts.push(`${r.latency_ms} ms`)
  if (r.loss) parts.push(t('services.loss', { pct: Math.round(r.loss * 100) }))
  if (r.cert_days != null) parts.push(t('services.check.certDays', { count: r.cert_days }))
  if (r.error) parts.push(r.error)
  else if (r.note) parts.push(r.note)
  return parts.join(' · ')
}
