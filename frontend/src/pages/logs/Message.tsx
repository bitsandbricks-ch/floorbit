import { Anchor, Text } from '@mantine/core'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SyslogLine } from '@/api/types'
import { filterlogText, parseFilterlog } from './filterlog'

/** A log line's message. A firewall's packet filter line reads as what it did instead of its comma
 *  list, which stays one click away (issue #1429). */
export function Message({ line }: { line: SyslogLine }) {
  const { t } = useTranslation()
  const [raw, setRaw] = useState(false)
  const parsed = line.program === 'filterlog' ? parseFilterlog(line.message) : null
  const program = line.program && <Text span c="dimmed" inherit>{line.program}: </Text>
  if (!parsed) return <>{program}{line.message}</>
  return (
    <>
      {program}
      <Text span inherit c={parsed.action === 'block' ? 'down' : undefined}>{filterlogText(parsed)}</Text>{' '}
      <Anchor component="button" type="button" size="xs" onClick={() => setRaw((r) => !r)} aria-expanded={raw}>
        {raw ? t('logFilterlog.hideRaw') : t('logFilterlog.showRaw')}
      </Anchor>
      {raw && <Text size="xs" c="dimmed" ff="monospace" style={{ overflowWrap: 'anywhere' }}>{line.message}</Text>}
    </>
  )
}
