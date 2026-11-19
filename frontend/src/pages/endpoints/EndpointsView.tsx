import { Button, Group, Stack, Text, TextInput } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ViewProps } from '@/widgets/views'

/** Find an IP or MAC address from a dashboard: the answer opens on the IP and MAC page, which
 *  has the history and the seat. */
export default function EndpointsView({ expanded }: ViewProps) {
  const { t } = useTranslation()
  const [q, setQ] = useState('')
  const go = (e: React.FormEvent) => {
    e.preventDefault()
    if (q.trim().length >= 2) window.location.href = `/endpoints?q=${encodeURIComponent(q.trim())}`
  }
  return (
    <form onSubmit={go} role="search">
      <Stack gap="xs">
        {expanded && <Text size="sm" c="dimmed">{t('endpoints.intro')}</Text>}
        <Group gap="xs" wrap="nowrap" align="flex-end">
          <TextInput value={q} onChange={(e) => setQ(e.currentTarget.value)} placeholder={t('endpoints.placeholder')}
            aria-label={t('endpoints.placeholder')} leftSection={<IconSearch size={16} aria-hidden="true" />} style={{ flex: 1 }} />
          <Button type="submit" variant="default" disabled={q.trim().length < 2}>{t('endpoints.find')}</Button>
        </Group>
      </Stack>
    </form>
  )
}
