import type { ProblemDetail } from '@/api/types'

type T = (k: string, o?: Record<string, unknown>) => string

/** Where to look next for a problem: what it points at, then its device, seat, logs and machines.
 *  The problem page and the notifications panel show the same list. */
export function problemPlaces(d: ProblemDetail, t: T): { label: string; href: string }[] {
  const { problem: p, device } = d
  return [
    ...(p.link ? [{ label: t('problem.source'), href: p.link }] : []),
    ...(device ? [{ label: t('problem.device', { name: device.name }), href: `/inventory/devices/${encodeURIComponent(device.id)}` }] : []),
    ...(p.seat ? [{ label: t('problem.seatOnPlan', { seat: p.seat }), href: `/plan?seat=${encodeURIComponent(p.seat)}` }] : []),
    ...(p.device && !p.seat ? [{ label: t('problem.onPlan', { name: p.device }), href: `/plan?switch=${encodeURIComponent(p.device)}` }] : []),
    ...(d.may_see_people && (p.seat || p.device) ? [{
      label: t('problem.logs'), href: p.seat ? `/logs?seat=${encodeURIComponent(p.seat)}` : `/logs?device=${encodeURIComponent(p.device ?? '')}` }] : []),
    ...(d.may_see_people && p.seat ? [{ label: t('problem.machines'), href: `/endpoints?seat=${encodeURIComponent(p.seat)}` }] : []),
  ]
}
