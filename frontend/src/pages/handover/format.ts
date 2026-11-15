import type { HandoverData, HandoverIncident } from '@/api/types'

/** Fri 14:05: shifts span midnight, so the day is part of the time. */
export function when(ts: number): string {
  return new Date(ts * 1000).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })
}

type T = (k: string, o?: Record<string, unknown>) => string

/** Who fixed how many this shift, most first; null is the incidents nobody was named on (issue #348). */
export function fixedBy(fixed: HandoverIncident[]): { who: string | null; count: number }[] {
  const by = new Map<string | null, number>()
  for (const i of fixed) by.set(i.assignee || null, (by.get(i.assignee || null) ?? 0) + 1)
  return [...by].map(([who, count]) => ({ who, count }))
    .sort((a, b) => b.count - a.count || (a.who === null ? 1 : b.who === null ? -1 : a.who.localeCompare(b.who)))
}

/** "By: kim 2 · ana 1 · nobody named 1", for the page and the copied text alike. */
export function byLine(fixed: HandoverIncident[], t: T): string {
  return t('handover.fixedBy', { list: fixedBy(fixed).map((f) => `${f.who ?? t('handover.nobodyNamed')} ${f.count}`).join(' · ') })
}

/** The summary as plain text, for crews that hand over in a chat or by mail rather than Discord (issue #220). */
export function summaryText(d: HandoverData, note: string, t: T, length: (s: number) => string): string {
  const where = (i: HandoverIncident) => i.where.kind === 'seat' ? t('incidents.seat', { seat: i.where.name })
    : i.where.kind === 'circuit' ? t('incidents.circuit', { name: i.where.name }) : t('incidents.switch', { name: i.where.name })
  const item = (i: HandoverIncident) => `- ${i.title} (${[where(i), i.assignee, i.match].filter(Boolean).join(', ')})`
  const c = d.counts
  const lines = [
    `${t('handover.title')}: ${t('handover.since', { when: when(d.since) })}`,
    `${t('handover.open')}: ${c.open}${c.waiting ? ` (${t('handover.waiting', { count: c.waiting })})` : ''} · ${t('handover.opened')}: ${c.opened} · ${t('handover.fixed')}: ${c.fixed}`
      + `${c.median_fix_s != null ? ` (${t('handover.halfWithin', { d: length(Math.max(60, c.median_fix_s)) })})` : ''} · `
      + `${t('handover.outages')}: ${c.outages} · ${t('handover.problems')}: ${c.problems}`,
    '',
    `${t('handover.stillOpen')}:`,
    ...(d.incidents.open.length ? d.incidents.open.map(item) : [t('handover.noneOpen')]),
  ]
  if (d.incidents.fixed.length) lines.push('', `${t('handover.fixedThisShift')}:`, byLine(d.incidents.fixed, t), ...d.incidents.fixed.map(item))
  if (d.outages.length) {
    lines.push('', `${t('handover.outagesTitle')}:`, ...d.outages.map((o) => `- ${o.name}: ${o.back_at
      ? t('handover.wasDown', { when: when(o.down_at), for: length(o.down_s) })
      : t('handover.stillDown', { when: when(o.down_at), for: length(o.down_s) })}`))
  }
  if (d.notice) lines.push('', `${t('handover.noticeUp')}: ${d.notice.text}`)
  if (d.mutes?.length) {
    lines.push('', `${t('handover.mutedTitle')}:`, ...d.mutes.map((m) => `- ${m.name}, ${t('handover.mutedUntil', { until: when(m.until), who: m.by ?? '?' })}`
      + (m.reason ? ` (${m.reason})` : '')))
  }
  if (d.gear?.length) {
    lines.push('', `${t('handover.gearTitle', { count: d.counts.gear_out ?? 0 })}:`, ...d.gear.map((g) => `- ${g.to}: ${g.names.join(', ')}`))
  }
  if (d.coming_up?.length) {
    lines.push('', `${t('handover.comingUp')}:`, ...d.coming_up.map((i) => `- ${when(i.start)} ${i.title}${i.where ? ` (${i.where})` : ''}`))
  }
  if (note.trim()) lines.push('', `${t('handover.note')}:`, note.trim())
  return lines.join('\n')
}
