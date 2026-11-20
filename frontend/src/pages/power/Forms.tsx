import { Alert, Button, Group, Input, MultiSelect, NumberInput, SegmentedControl, Select, Stack, TextInput } from '@mantine/core'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { Circuit, CircuitFeed, Phase, PowerBoard, PowerOverview } from '@/api/types'

const PHASES: Phase[] = ['L1', 'L2', 'L3', '3P']

function Buttons({ busy, extra }: { busy: boolean; extra?: ReactNode }) {
  const { t } = useTranslation()
  return (
    <Group justify="space-between">
      {extra ?? <span />}
      <Button type="submit" loading={busy}>{t('power.save')}</Button>
    </Group>
  )
}

const num = (v: string | number) => (v === '' ? null : Number(v))

/** A distribution board's name, where it is and where it sits on the floor plan. The page that
 *  shows it mounts the form again (a key) when the board changes, so the fields start from it. */
export function BoardForm({ board, busy, error, extra, onSave }: {
  board: PowerBoard | null
  busy: boolean
  error: string | null
  extra?: ReactNode
  onSave: (body: Partial<PowerBoard>) => void
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(board?.name ?? '')
  const [location, setLocation] = useState(board?.location ?? '')
  const [x, setX] = useState<string | number>(board?.x ?? '')
  const [y, setY] = useState<string | number>(board?.y ?? '')
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSave({ name, location, x: num(x), y: num(y) }) }}>
      <Stack gap="sm">
        <TextInput label={t('power.boardName')} placeholder="DB-1" value={name} required maxLength={40} onChange={(e) => setName(e.currentTarget.value)} />
        <TextInput label={t('power.location')} value={location} maxLength={80} onChange={(e) => setLocation(e.currentTarget.value)} />
        <Group grow align="flex-end">
          <NumberInput label={t('power.x')} description={t('power.position')} min={0} max={100} value={x} onChange={setX} />
          <NumberInput label={t('power.y')} min={0} max={100} value={y} onChange={setY} />
        </Group>
        {error && <Alert color="down" role="alert">{error}</Alert>}
        <Buttons busy={busy} extra={extra} />
      </Stack>
    </form>
  )
}

// A feed is one MultiSelect value: "<block id>" for every row, "<block id>:<row>" for one row.
function toValues(feeds: CircuitFeed[]) {
  return feeds.flatMap((f) => (f.rows.length ? f.rows.map((r) => `${f.block}:${r}`) : [f.block]))
}

function toFeeds(values: string[]): CircuitFeed[] {
  const out = new Map<string, number[] | null>()
  for (const v of values) {
    const [block, row] = v.split(':')
    if (!row) out.set(block, null)
    else if (out.get(block) !== null) out.set(block, [...(out.get(block) ?? []), Number(row)])
  }
  return [...out].map(([block, rows]) => ({ block, rows: rows ?? [] }))
}

/** A circuit: its board, phase, fuse, meter and what it feeds. */
export function CircuitForm({ circuit, overview, switches, busy, error, extra, onSave, startBoard }: {
  circuit: Circuit | null
  startBoard?: string | null
  overview: PowerOverview
  switches: { id: string; name: string }[]
  busy: boolean
  error: string | null
  extra?: ReactNode
  onSave: (body: Record<string, unknown>) => void
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(circuit?.name ?? '')
  const [board, setBoard] = useState<string | null>(circuit?.board ?? startBoard ?? overview.boards[0]?.id ?? null)
  const [phase, setPhase] = useState<Phase>(circuit?.phase ?? 'L1')
  const [rating, setRating] = useState<string | number>(circuit?.rating_a ?? 16)
  const [meter, setMeter] = useState(circuit?.meter ?? '')
  const [feeds, setFeeds] = useState<string[]>(toValues(circuit?.blocks ?? []))
  const [fed, setFed] = useState<string[]>(circuit?.switches ?? [])
  const blockOptions = overview.blocks.map((b) => ({
    group: b.label || b.name,
    items: [
      { value: b.id, label: t('power.allRows', { name: b.label || b.name }) },
      ...Array.from({ length: b.rows }, (_, i) => ({ value: `${b.id}:${i + 1}`, label: t('power.row', { name: b.label || b.name, row: b.row_names?.[i] ?? i + 1 }) })),
    ],
  }))
  return (
    <form onSubmit={(e) => {
      e.preventDefault()
      onSave({ name, board, phase, rating_a: Number(rating), meter, blocks: toFeeds(feeds), switches: fed })
    }}>
      <Stack gap="sm">
        <Group grow>
          <TextInput label={t('power.circuitName')} placeholder="A row 1" value={name} required maxLength={40} onChange={(e) => setName(e.currentTarget.value)} />
          <Select label={t('power.board')} data={overview.boards.map((b) => ({ value: b.id, label: b.name }))} value={board} onChange={setBoard} required allowDeselect={false} />
        </Group>
        <Group grow align="flex-end">
          <Input.Wrapper label={t('power.phase')}>
            <SegmentedControl fullWidth aria-label={t('power.phase')} value={phase} onChange={(v) => setPhase(v as Phase)} data={PHASES} />
          </Input.Wrapper>
          <NumberInput label={t('power.rating')} min={1} max={400} value={rating} onChange={setRating} required />
        </Group>
        <TextInput label={t('power.meter')} description={t('power.meterHint')} value={meter} maxLength={60} onChange={(e) => setMeter(e.currentTarget.value)} />
        <MultiSelect label={t('power.rows')} data={blockOptions} value={feeds} onChange={setFeeds} searchable clearable />
        <MultiSelect label={t('power.switches')} data={switches.map((s) => ({ value: s.id, label: s.name }))} value={fed} onChange={setFed} searchable clearable />
        {error && <Alert color="down" role="alert">{error}</Alert>}
        <Buttons busy={busy} extra={extra} />
      </Stack>
    </form>
  )
}

/** Type in what the clamp meter or the board's display says. */
export function ReadingForm({ busy, error, extra, onSave }: {
  busy: boolean
  error: string | null
  extra?: ReactNode
  onSave: (body: { amps?: number; watts?: number }) => void
}) {
  const { t } = useTranslation()
  const [unit, setUnit] = useState<'amps' | 'watts'>('amps')
  const [value, setValue] = useState<string | number>('')
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSave({ [unit]: Number(value) }) }}>
      <Stack gap="sm">
        <SegmentedControl aria-label={t('power.unit')} value={unit} onChange={(v) => setUnit(v as 'amps' | 'watts')}
          data={[{ value: 'amps', label: t('power.amps') }, { value: 'watts', label: t('power.watts') }]} />
        <NumberInput label={t('power.value')} min={0} decimalScale={2} value={value} onChange={setValue} required data-autofocus
          rightSection={unit === 'amps' ? 'A' : 'W'} />
        {error && <Alert color="down" role="alert">{error}</Alert>}
        <Buttons busy={busy} extra={extra} />
      </Stack>
    </form>
  )
}
