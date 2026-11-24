import { Alert, Badge, Group, Paper, Stack, Text, TextInput } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { type FirewallLookup as Answer, useFirewallLookup } from '@/api/firewallLookup'

const TONE = { primary: 'up', failover: 'warn', unknown: 'gray', down: 'down' } as const

/** "Which firewall?": type an IP address or a seat, see the part of the range it is in and the
 *  firewall it goes through now. The seat panel links here with ?q=<seat>. */
export function FirewallLookup() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const asked = params.get('q') ?? ''
  const [text, setText] = useState(asked)
  const q = useFirewallLookup(asked)
  const ask = () => {
    const next = new URLSearchParams(params)
    if (text.trim()) next.set('q', text.trim())
    else next.delete('q')
    setParams(next, { replace: true })
  }
  return (
    <Paper withBorder radius="lg" p="md" component="section" aria-label={t('firewalls.lookup.title')}>
      <form onSubmit={(e) => { e.preventDefault(); ask() }}>
        <Group align="flex-end" gap="md" wrap="wrap">
          <TextInput label={t('firewalls.lookup.title')} placeholder={t('firewalls.lookup.placeholder')} value={text}
            onChange={(e) => setText(e.currentTarget.value)} onBlur={ask} leftSection={<IconSearch size={16} />}
            style={{ flex: '0 1 320px' }} spellCheck={false} autoComplete="off" />
          <Stack gap={2} style={{ flex: '1 1 320px', minWidth: 0 }} aria-live="polite">
            {!asked && <Text size="sm" c="dimmed">{t('firewalls.lookup.help')}</Text>}
            {asked && q.isPending && <Text size="sm" c="dimmed">…</Text>}
            {q.error && <Alert color="warn" p="xs">{q.error.message}</Alert>}
            {q.data && <Result a={q.data} />}
          </Stack>
        </Group>
      </form>
    </Paper>
  )
}

function Result({ a }: { a: Answer }) {
  const { t } = useTranslation()
  const who = a.seat ? t('firewalls.lookup.seat', { seat: a.seat }) : a.query
  if (!a.found || !a.state) return <Text size="sm">{t('firewalls.lookup.none', { who })}</Text>
  const where = a.part ? t('firewalls.lookup.inPart', { range: a.range || a.cidr, part: a.part }) : (a.range || '')
  return (
    <>
      <Group gap="xs" wrap="wrap">
        <Text size="sm" fw={600}>
          {a.state === 'down'
            ? t('firewalls.lookup.down', { who, intended: a.intended })
            : t('firewalls.lookup.goes', { who, now: a.now })}
        </Text>
        <Badge size="sm" variant="light" color={TONE[a.state]} tt="none">{t(`firewalls.lookup.state.${a.state}`, { intended: a.intended })}</Badge>
      </Group>
      {where && <Text size="xs" c="dimmed" ff={a.part ? 'monospace' : undefined}>{where}</Text>}
      {a.fallback && a.fallback.length > 0 && (
        <Text size="xs" c="dimmed">{t('firewalls.lookup.fallback', { list: a.fallback.join(', ') })}</Text>
      )}
    </>
  )
}
