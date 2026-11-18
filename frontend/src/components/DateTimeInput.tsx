import { ActionIcon, Button, Group, Popover, Select, SimpleGrid, Stack, Text, TextInput, UnstyledButton } from '@mantine/core'
import { IconCalendar, IconChevronLeft, IconChevronRight } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { editText, parseTyped, parseValue, toValue, type Parts } from '@/lib/dateTimeText'
import { formatWhen } from '@/lib/time'

// A date-and-time field in 24-hour time and Swiss day order, in place of the browser's datetime-local
// input, which shows "11/16/2026, 04:00 PM" to English browsers. Same value ("YYYY-MM-DDTHH:MM", local
// time), so a page swaps one for the other. Ported from Seatbit's date-time-picker (by Mike).

type Props = {
  label: string
  value: string
  onChange: (value: string) => void
  required?: boolean
  disabled?: boolean
  w?: number | string
}

const pad = (n: number) => String(n).padStart(2, '0')
const HOURS = Array.from({ length: 24 }, (_, h) => ({ value: String(h), label: pad(h) }))
const QUICK = [[8, 0], [12, 0], [18, 0], [20, 0]] as const
// Picking a day before a time: noon is the least wrong guess for "some time that day".
const NOON = { hh: 12, mm: 0 }

function minutes(mm: number) {
  const steps = Array.from({ length: 12 }, (_, i) => i * 5)
  if (!steps.includes(mm)) steps.push(mm)
  return steps.sort((a, b) => a - b).map((m) => ({ value: String(m), label: pad(m) }))
}

/** The weeks of a month, Monday first, as day numbers (null outside the month). */
function weeks(y: number, m: number): (number | null)[] {
  const first = (new Date(y, m, 1).getDay() + 6) % 7
  const days = new Date(y, m + 1, 0).getDate()
  const cells: (number | null)[] = Array.from({ length: first }, () => null)
  for (let d = 1; d <= days; d++) cells.push(d)
  while (cells.length % 7) cells.push(null)
  return cells
}

export function DateTimeInput({ label, value, onChange, required, disabled, w }: Props) {
  const { t } = useTranslation()
  const [text, setText] = useState(editText(value))
  const [typing, setTyping] = useState(false)
  const [bad, setBad] = useState(false)
  const [open, setOpen] = useState(false)
  const picked = parseValue(value)
  const now = new Date()
  const [month, setMonth] = useState(() => ({ y: picked?.y ?? now.getFullYear(), m: picked?.m ?? now.getMonth() }))

  // Follow the value when the page changes it (a reset, an item opened for editing), not while typing.
  const [seen, setSeen] = useState(value)
  if (seen !== value) { setSeen(value); if (!typing) setText(editText(value)) }

  const commit = () => {
    setTyping(false)
    if (!text.trim()) { setBad(false); if (value) onChange(''); return }
    const p = parseTyped(text, picked ?? NOON)
    setBad(!p)
    if (p) { onChange(toValue(p)); setText(editText(toValue(p))) }
  }
  const put = (p: Parts) => { setBad(false); onChange(toValue(p)) }
  const time = picked ?? { ...NOON }
  const pickDay = (d: number) => put({ y: month.y, m: month.m, d, hh: time.hh, mm: time.mm })
  const pickTime = (hh: number, mm: number) => put({ y: picked?.y ?? now.getFullYear(), m: picked?.m ?? now.getMonth(), d: picked?.d ?? now.getDate(), hh, mm })
  const shift = (by: number) => setMonth(({ y, m }) => ({ y: y + Math.floor((m + by) / 12), m: (m + by + 12) % 12 }))
  const monday = new Date(2024, 0, 1)   // a Monday, for the weekday heads
  const isToday = (d: number) => d === now.getDate() && month.m === now.getMonth() && month.y === now.getFullYear()

  return (
    <Popover opened={open} onChange={setOpen} position="bottom-start" shadow="md" trapFocus withinPortal>
      <Popover.Target>
        <TextInput label={label} required={required} disabled={disabled} w={w} value={text}
          placeholder={t('dateTime.placeholder')} autoComplete="off"
          error={bad ? t('dateTime.invalid') : undefined}
          onChange={(e) => { setTyping(true); setText(e.currentTarget.value) }}
          onBlur={commit}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commit() } }}
          rightSection={
            <ActionIcon variant="subtle" color="gray" disabled={disabled} aria-label={t('dateTime.pick')}
              onClick={() => { if (picked) setMonth({ y: picked.y, m: picked.m }); setOpen((o) => !o) }}>
              <IconCalendar size={16} />
            </ActionIcon>
          } />
      </Popover.Target>
      <Popover.Dropdown p="sm">
        <Stack gap="xs" w={260}>
          <Group justify="space-between" wrap="nowrap">
            <ActionIcon variant="subtle" color="gray" aria-label={t('dateTime.prevMonth')} onClick={() => shift(-1)}><IconChevronLeft size={16} /></ActionIcon>
            <Text fw={600} size="sm" aria-live="polite">{formatWhen(new Date(month.y, month.m, 1), { month: 'long', year: 'numeric' })}</Text>
            <ActionIcon variant="subtle" color="gray" aria-label={t('dateTime.nextMonth')} onClick={() => shift(1)}><IconChevronRight size={16} /></ActionIcon>
          </Group>
          <SimpleGrid cols={7} spacing={2} verticalSpacing={2}>
            {Array.from({ length: 7 }, (_, i) => (
              <Text key={`h${i}`} size="xs" c="dimmed" ta="center" aria-hidden>
                {formatWhen(new Date(monday.getTime() + i * 86400000), { weekday: 'short' })}
              </Text>
            ))}
            {weeks(month.y, month.m).map((d, i) => d === null ? <span key={i} /> : (
              <UnstyledButton key={i} onClick={() => pickDay(d)} className="fb-day"
                data-picked={picked && picked.d === d && picked.m === month.m && picked.y === month.y || undefined}
                data-today={isToday(d) || undefined}
                aria-label={formatWhen(new Date(month.y, month.m, d), { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}>
                {d}
              </UnstyledButton>
            ))}
          </SimpleGrid>
          <Group gap="xs" grow>
            <Select label={t('dateTime.hour')} size="xs" data={HOURS} value={String(time.hh)} allowDeselect={false}
              comboboxProps={{ withinPortal: false }} onChange={(v) => pickTime(Number(v ?? 0), time.mm)} />
            <Select label={t('dateTime.minute')} size="xs" data={minutes(time.mm)} value={String(time.mm)} allowDeselect={false}
              comboboxProps={{ withinPortal: false }} onChange={(v) => pickTime(time.hh, Number(v ?? 0))} />
          </Group>
          <Group gap={4}>
            {QUICK.map(([hh, mm]) => (
              <Button key={hh} size="compact-xs" variant={time.hh === hh && time.mm === mm ? 'light' : 'default'}
                onClick={() => pickTime(hh, mm)}>{`${pad(hh)}:${pad(mm)}`}</Button>
            ))}
          </Group>
          <Group justify="space-between" gap="xs">
            <Group gap={4}>
              <Button size="compact-sm" variant="subtle" onClick={() => { setMonth({ y: now.getFullYear(), m: now.getMonth() }); put({ y: now.getFullYear(), m: now.getMonth(), d: now.getDate(), hh: time.hh, mm: time.mm }) }}>{t('dateTime.today')}</Button>
              {!required && <Button size="compact-sm" variant="subtle" color="gray" onClick={() => { setBad(false); onChange(''); setOpen(false) }}>{t('dateTime.clear')}</Button>}
            </Group>
            <Button size="compact-sm" onClick={() => setOpen(false)}>{t('dateTime.done')}</Button>
          </Group>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  )
}
