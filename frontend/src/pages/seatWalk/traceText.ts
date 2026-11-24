import { useTranslation } from 'react-i18next'
import type { TraceStep } from '@/api/seatWalkTrace'

/** The text key of a step: some codes say more by their result or state. */
export function stepKey(s: TraceStep): string {
  if (s.code === 'snmpTodo') return `seatWalkTrace.snmpTodo.${String(s.args.why ?? 'no_segment')}`
  if (s.args.result) return `seatWalkTrace.${s.code}.${String(s.args.result)}`
  if (s.code === 'mac' || s.code === 'snmpMac') return `seatWalkTrace.${s.code}.${s.state === 'ok' ? 'ok' : 'no'}`
  return `seatWalkTrace.${s.code}`
}

/** One step in words. */
export function useStepText() {
  const { t } = useTranslation()
  return (s: TraceStep) => {
    const args: Record<string, string | number> = {}
    for (const [k, v] of Object.entries(s.args)) {
      if (Array.isArray(v)) args[k] = v.length ? v.join(', ') : '–'
      else if (v !== null && v !== undefined) args[k] = v
    }
    if (typeof s.args.group === 'string') args.group = t(`seatWalkTrace.group.${s.args.group}`)
    if (typeof s.args.how === 'string') args.how = t(`seatWalkTrace.how.${s.args.how}`, { defaultValue: s.args.how })
    args.ip ??= t('seatWalkTrace.hidden')
    args.mac ??= t('seatWalkTrace.hidden')
    return t(stepKey(s), args)
  }
}

/** The steps of the last try only: what the flow strip and the short view show. */
export function lastTry(steps: TraceStep[]): TraceStep[] {
  const i = steps.map((s) => s.code).lastIndexOf('wait')
  return i < 0 ? steps : steps.slice(i + 1)
}

