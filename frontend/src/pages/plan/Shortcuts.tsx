import { Group, Kbd, Modal, Table, Text, Title } from '@mantine/core'
import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import { Attribution } from '@/components/Attribution'
import { EDIT_SHORTCUTS, type KeyRow } from './edit/shortcuts'

// Each row: the keys (alternatives joined by "or") and what they do. Mirrors docs/seats.md.
const ROWS: KeyRow[] = [
  [[['←', '↑', '→', '↓']], 'arrows'],
  [[['Enter'], ['Space']], 'open'],
  [[['Esc']], 'close'],
  [[['B']], 'block'],
  [[['1'], ['2'], ['3'], ['4']], 'presets'],
  [[['L']], 'list'],
  [[[']']], 'side'],
  [[['Shift', '←↑→↓']], 'pan'],
  [[['+'], ['-'], ['0']], 'zoom'],
  [[['/']], 'find'],
  [[['?']], 'help'],
]

// Crew who may change the plan take a tool up with its key (B stays the seat's block here).
const TOOL_ROW: KeyRow[] = [[[['V'], ['W'], ['Z'], ['S']], 'tools']]

/** The plan's keyboard shortcuts in one list, opened with "?" (issue #224); while editing, the
 *  editor's keys by section. */
export function Shortcuts({ opened, onClose, editing = false, canEdit = false }: { opened: boolean; onClose: () => void; editing?: boolean; canEdit?: boolean }) {
  const { t } = useTranslation()
  return (
    <Modal opened={opened} onClose={onClose} title={t(editing ? 'plan.shortcuts.editTitle' : 'plan.shortcuts.title')} size="lg">
      <Text size="sm" c="dimmed" mb="sm">{t(editing ? 'plan.shortcuts.editIntro' : 'plan.shortcuts.intro')}</Text>
      {/* The plan's how-to used to sit under the map; the map now fills the page, so it lives here. */}
      {!editing && <Text size="sm" mb="sm">{t('plan.help')}</Text>}
      {editing
        ? EDIT_SHORTCUTS.map(([section, rows]) => (
          <div key={section}>
            <Title order={4} size="sm" mt="sm">{t(`plan.shortcuts.edit.${section}`)}</Title>
            <Keys rows={rows.map(([k, what]) => [k, what.startsWith('tool.') ? t(`plan.edit.${what}`) : t(`plan.shortcuts.edit.${what}`)])} />
          </div>
        ))
        : <Keys rows={[...ROWS, ...(canEdit ? TOOL_ROW : [])].map(([k, what]) => [k, t(`plan.shortcuts.${what}`)])} />}
      <Attribution compact />
    </Modal>
  )
}

function Keys({ rows }: { rows: KeyRow[] }) {
  const { t } = useTranslation()
  return (
    <Table>
      <Table.Tbody>
        {rows.map(([alts, text]) => (
          <Table.Tr key={text}>
            <Table.Td style={{ whiteSpace: 'nowrap', width: '40%' }}>
              <Group gap={6} wrap="nowrap">
                {alts.map((keys, n) => (
                  <Fragment key={n}>
                    {n > 0 && <Text span size="xs" c="dimmed">{t('plan.shortcuts.or')}</Text>}
                    {keys.map((k) => <Kbd key={k}>{k}</Kbd>)}
                  </Fragment>
                ))}
              </Group>
            </Table.Td>
            <Table.Td>{text}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}
