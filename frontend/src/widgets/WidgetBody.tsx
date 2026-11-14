import { Group, Table, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { Tone, Widget } from '@/api/types'
import { Sparkline } from './Sparkline'

// A widget is data (floorbit/plugins/widgets.py checks it on the server). Everything a plugin
// sends is drawn as text: React escapes it, and nothing here sets HTML.

const toneClass = (tone: Tone | undefined) => (tone ? `fb-tone-${tone}` : undefined)

function Stat({ value, unit, tone }: { value: number | string | undefined; unit?: string; tone?: Tone }) {
  return (
    <Text fz={28} fw={700} lh={1.1} className={toneClass(tone)} style={{ fontVariantNumeric: 'tabular-nums' }}>
      {value ?? '–'}
      {unit && (
        <Text span fz="sm" fw={500} c="dimmed" ml={4}>
          {unit}
        </Text>
      )}
    </Text>
  )
}

export function WidgetBody({ widget }: { widget: Widget }) {
  const { t } = useTranslation()
  switch (widget.type) {
    case 'stat':
      return <Stat value={widget.value} unit={widget.unit} tone={widget.tone} />
    case 'status':
      return (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 6 }}>
          {widget.items.map((item, i) => (
            <li key={i}>
              <Group gap={8} wrap="nowrap">
                <span className={`fb-dot ${item.state}`} role="img" aria-label={item.state} title={item.state} />
                <Text size="sm" style={{ flex: 1, minWidth: 0 }} truncate>
                  {item.label}
                </Text>
                <Text size="sm" c="dimmed" ff="monospace">
                  {item.detail}
                </Text>
              </Group>
            </li>
          ))}
        </ul>
      )
    case 'list':
      return (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 6 }}>
          {widget.items.map((item, i) => (
            <li key={i}>
              <Group gap={8} justify="space-between" wrap="nowrap">
                <Text size="sm" truncate>
                  {item.label}
                </Text>
                <Text size="sm" ff="monospace" className={toneClass(item.tone)} c={item.tone ? undefined : 'dimmed'}>
                  {item.value}
                </Text>
              </Group>
            </li>
          ))}
        </ul>
      )
    case 'table':
      return (
        <Table.ScrollContainer minWidth={320}>
          <Table striped highlightOnHover fz="sm">
            <Table.Thead>
              <Table.Tr>
                {widget.columns.map((c) => (
                  <Table.Th key={c.key}>{c.label}</Table.Th>
                ))}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {widget.rows.map((row, i) => (
                <Table.Tr key={i}>
                  {widget.columns.map((c) => (
                    <Table.Td key={c.key}>{row[c.key]}</Table.Td>
                  ))}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )
    case 'sparkline':
      return (
        <>
          {widget.value != null && <Stat value={widget.value} unit={widget.unit} />}
          <Sparkline points={widget.points} min={widget.min} max={widget.max} />
        </>
      )
    default:
      return (
        <Text size="sm" c="red">
          {t('dashboard.cantDraw')}
        </Text>
      )
  }
}
