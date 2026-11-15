import { Group, Kbd, Modal, Table, Text } from '@mantine/core'
import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'

// Each row: the keys (alternatives joined by "or") and what they do. Mirrors docs/seats.md.
const ROWS: [string[][], string][] = [
  [[['←', '↑', '→', '↓']], 'arrows'],
  [[['Enter'], ['Space']], 'open'],
  [[['Esc']], 'close'],
  [[['B']], 'block'],
  [[['Shift', '←↑→↓']], 'pan'],
  [[['+'], ['-'], ['0']], 'zoom'],
  [[['/']], 'find'],
  [[['?']], 'help'],
]

/** The plan's keyboard shortcuts in one list, opened with "?" (issue #224). */
export function Shortcuts({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  return (
    <Modal opened={opened} onClose={onClose} title={t('plan.shortcuts.title')} size="lg">
      <Text size="sm" c="dimmed" mb="sm">{t('plan.shortcuts.intro')}</Text>
      <Table>
        <Table.Tbody>
          {ROWS.map(([alts, key]) => (
            <Table.Tr key={key}>
              <Table.Td style={{ whiteSpace: 'nowrap' }}>
                <Group gap={6} wrap="nowrap">
                  {alts.map((keys, n) => (
                    <Fragment key={n}>
                      {n > 0 && <Text span size="xs" c="dimmed">{t('plan.shortcuts.or')}</Text>}
                      {keys.map((k) => <Kbd key={k}>{k}</Kbd>)}
                    </Fragment>
                  ))}
                </Group>
              </Table.Td>
              <Table.Td>{t(`plan.shortcuts.${key}`)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Modal>
  )
}
