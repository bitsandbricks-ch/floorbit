import { ActionIcon, CopyButton, Group, Paper, SegmentedControl, Stack, Text, Tooltip } from '@mantine/core'
import { IconCheck, IconCopy } from '@tabler/icons-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TraceState, TraceStep } from '@/api/seatWalkTrace'
import { lastTry, useStepText } from './traceText'
import './Trace.css'

const MARK: Record<TraceState, string> = { ok: '✓', no: '✗', skip: '↷', warn: '!', run: '●' }

const time = (at: number) => {
  const d = new Date(at)
  const pad = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`
}

/** Everything Floorbit did for this seat, as it happens (issue #1359). */
export function TraceConsole({ steps, running }: { steps: TraceStep[]; running: boolean }) {
  const { t } = useTranslation()
  const text = useStepText()
  const [view, setView] = useState<'steps' | 'all'>('steps')
  // Steps: the tries before the last one shrink to one line each, so a long wait stays readable.
  const shown = useMemo(() => {
    if (view === 'all') return steps
    const out: TraceStep[] = []
    for (const s of steps) {
      const prev = out[out.length - 1]
      if (s.code === 'wait' && prev?.code === 'wait') out[out.length - 1] = s
      else out.push(s)
    }
    return out
  }, [steps, view])
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = box.current
    if (el) el.scrollTop = el.scrollHeight
  }, [shown.length])
  const plain = steps.map((s) => `${time(s.at)} ${MARK[s.state]} ${text(s)}${s.ms !== undefined ? ` (${s.ms} ms)` : ''}`).join('\n')
  return (
    <Paper withBorder radius="lg" p="md" className="walk-trace">
      <Stack gap="xs">
        <Group justify="space-between" wrap="nowrap">
          <Text fw={600}>{t('seatWalkTrace.title')}</Text>
          <Group gap="xs" wrap="nowrap">
            <SegmentedControl size="xs" value={view} onChange={(v) => setView(v as 'steps' | 'all')}
              data={[{ value: 'steps', label: t('seatWalkTrace.steps') }, { value: 'all', label: t('seatWalkTrace.all') }]} />
            <CopyButton value={plain}>
              {({ copied, copy }) => (
                <Tooltip label={copied ? t('seatWalkTrace.copied') : t('seatWalkTrace.copy')}>
                  <ActionIcon variant="subtle" color="gray" onClick={copy} aria-label={t('seatWalkTrace.copy')}>
                    {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                  </ActionIcon>
                </Tooltip>
              )}
            </CopyButton>
          </Group>
        </Group>
        <div ref={box} className="walk-trace-lines" role="log" aria-live="polite" aria-label={t('seatWalkTrace.title')}>
          {!shown.length && <Text size="sm" c="dimmed">{t('seatWalkTrace.empty')}</Text>}
          {shown.map((s, i) => (
            <div key={`${s.at}-${i}`} className="walk-trace-line" data-state={s.state}>
              <span className="walk-trace-time">{time(s.at)}</span>
              <span className="walk-trace-mark" aria-hidden>{MARK[s.state]}</span>
              <span>{text(s)}</span>
              <span className="walk-trace-ms">{s.ms !== undefined ? `${s.ms} ms` : ''}</span>
            </div>
          ))}
          {running && <div className="walk-trace-cursor" aria-hidden>▍</div>}
        </div>
      </Stack>
    </Paper>
  )
}

type Stage = { id: string; label: string; detail: string; state: 'done' | 'now' | 'no' | 'wait' | 'skip' }

/** Laptop → MAC → tables → switches (row, block, VLAN, SSH) → seat: where the lookup is now. */
export function FlowStrip({ steps, running, seat }: { steps: TraceStep[]; running: boolean; seat: string }) {
  const { t } = useTranslation()
  const stages = useMemo<Stage[]>(() => {
    const all = lastTry(steps)
    const one = (codes: string[]) => all.filter((s) => codes.includes(s.code))
    // The laptop and its MAC are found once per Locate; the switches are asked again each try.
    const laptop = steps.find((s) => s.code === 'hello' || s.code === 'macTyped')
    const mac = [...all, ...steps].filter((s) => ['macTyped', 'macReused', 'mac', 'snmpMac'].includes(s.code))[0]
    const tables = one(['monitoring', 'monitoringOff'])[0]
    const ask = one(['snmpAsk'])[0]
    const switches = one(['snmpSwitch'])
    const ssh = one(['sshAsk', 'sshSwitch'])
    const found = one(['found'])[0]
    const ended = !running || !!found
    const out: Stage[] = [{
      id: 'laptop', label: t('seatWalkTrace.flow.laptop'),
      detail: laptop ? String(laptop.args.agent ?? laptop.args.mac ?? '') : '', state: laptop ? 'done' : 'wait',
    }, {
      id: 'mac', label: t('seatWalkTrace.flow.mac'), detail: mac?.state === 'ok' ? t('seatWalkTrace.flow.known') : '',
      state: !mac ? 'wait' : mac.state === 'ok' ? 'done' : 'no',
    }, {
      id: 'tables', label: t('seatWalkTrace.flow.tables'),
      detail: tables ? t(tables.code === 'monitoringOff' ? 'seatWalkTrace.flow.off' : `seatWalkTrace.flow.${tables.state}`) : '',
      state: !tables ? 'wait' : tables.code === 'monitoringOff' || tables.state === 'skip' ? 'skip' : tables.state === 'ok' ? 'done' : 'no',
    }]
    for (const group of ['row', 'block', 'vlan'] as const) {
      const names = ask ? (group === 'vlan' ? Number(ask.args.others ?? 0) : (ask.args[group] as string[] | undefined)?.length ?? 0) : 0
      const said = switches.filter((s) => s.args.group === group)
      const hit = said.find((s) => s.state === 'ok')
      const asking = !!ask && !switches.length && running && !found
      out.push({
        id: group, label: t(`seatWalkTrace.flow.${group}`),
        detail: ask ? t('seatWalkTrace.flow.switches', { count: names }) : '',
        state: hit ? 'done' : asking && (group === 'row' || names) ? (group === 'row' ? 'now' : 'wait')
          : said.length ? 'no' : ask && !names ? 'skip' : ask && switches.length ? 'skip' : 'wait',
      })
    }
    if (ssh.length) {
      const hit = ssh.find((s) => s.code === 'sshSwitch' && s.state === 'ok')
      out.push({
        id: 'ssh', label: t('seatWalkTrace.flow.ssh'), detail: String(ssh[0].args.switches ?? ''),
        state: hit ? 'done' : ssh.some((s) => s.code === 'sshSwitch') ? 'no' : running ? 'now' : 'no',
      })
    }
    out.push({
      id: 'seat', label: seat, detail: found ? `${String(found.args.switch)} ${String(found.args.port)}` : '',
      state: found ? 'done' : ended ? 'no' : 'wait',
    })
    // While running, the first stage still waiting after the last one with an answer is where it is now.
    if (running && !found && !out.some((s) => s.state === 'now')) {
      const last = out.map((s) => s.state !== 'wait').lastIndexOf(true)
      const next = out[last + 1]
      if (next && next.state === 'wait') next.state = 'now'
    }
    return out
  }, [steps, running, seat, t])
  return (
    <div className="walk-flow" role="list" aria-label={t('seatWalkTrace.flow.title')}>
      {stages.map((s, i) => (
        <div key={s.id} className="walk-flow-item" role="listitem">
          {i > 0 && <span className="walk-flow-arrow" data-state={s.state} aria-hidden />}
          <div className="walk-flow-node" data-state={s.state}>
            <Text size="xs" c="dimmed" tt="uppercase" fw={600} lh={1.2}>{s.label}</Text>
            <Text size="sm" fw={600} lh={1.3} truncate>{s.detail || ' '}</Text>
          </div>
        </div>
      ))}
    </div>
  )
}

/** Where the laptop goes and what the page looks for (issue #1358). */
export function LaptopStrip({ agentUrl, ip, mac, agent }: {
  agentUrl: string | null; ip: string | null; mac: string | null; agent: string | null
}) {
  const { t } = useTranslation()
  return (
    <div className="walk-strip">
      <Paper withBorder radius="md" p="sm" className="walk-strip-cell walk-strip-wide">
        <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{t('seatWalkTrace.strip.open')}</Text>
        <Group gap={6} wrap="nowrap">
          <Text ff="monospace" c={agentUrl ? 'trace' : 'dimmed'} truncate>{agentUrl ?? t('seatWalkTrace.strip.noAgent')}</Text>
          {agentUrl && (
            <CopyButton value={agentUrl}>
              {({ copied, copy }) => (
                <ActionIcon size="sm" variant="subtle" color="gray" onClick={copy} aria-label={t('seatWalkTrace.copy')}>
                  {copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
                </ActionIcon>
              )}
            </CopyButton>
          )}
        </Group>
      </Paper>
      <Paper withBorder radius="md" p="sm" className="walk-strip-cell">
        <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{t('seatWalkTrace.strip.laptop')}</Text>
        <Text ff="monospace" truncate>{ip || mac ? [ip, mac].filter(Boolean).join(' · ') : t('seatWalkTrace.strip.unknown')}</Text>
      </Paper>
      <Paper withBorder radius="md" p="sm" className="walk-strip-cell">
        <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{t('seatWalkTrace.strip.agent')}</Text>
        <Text ff="monospace" truncate>{agent ?? '–'}</Text>
      </Paper>
    </div>
  )
}
