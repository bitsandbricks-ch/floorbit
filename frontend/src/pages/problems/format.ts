import type { AlertMute, Problem } from '@/api/types'
import { clock } from '@/lib/time'

type T = (k: string, o?: Record<string, unknown>) => string


/** Plain text for a chat or a ticket: what the page shows, in its order (issue #280). */
export function problemsText(problems: Problem[], mutes: AlertMute[], t: T, ago: (ts: number) => string, now = Date.now() / 1000): string {
  // Muted ones are counted as muted only, like the cards on the page.
  const live = problems.filter((p) => !p.muted)
  const down = live.filter((p) => p.level === 'down').length
  const lines = [
    `${t('problems.title')} ${clock(now)}: ${t('problems.count.down', { count: down })} · `
      + `${t('problems.count.warn', { count: live.length - down })} · ${t('problems.count.muted', { count: mutes.length })}`,
  ]
  if (!problems.length) lines.push(t('problems.none'))
  for (const p of problems) {
    const bits = [p.where, p.since ? t('problems.since', { ago: ago(p.since) }) : null,
      p.muted ? t('problems.mutedUntil', { time: clock(p.muted.until), who: p.muted.by ?? '?' }) : null]
    lines.push(`- [${t(`problems.kind.${p.kind}`)}] ${p.title} (${bits.filter(Boolean).join(', ')})`)
  }
  if (mutes.length) {
    lines.push('', `${t('problems.mutes')}:`, ...mutes.map((m) => `- ${m.name}, ${t('problems.mutedUntil', { time: clock(m.until), who: m.by ?? '?' })}`
      + (m.reason ? ` (${m.reason})` : '')))
  }
  return lines.join('\n')
}

/** Worst first (issue #883): down, then to look at, then muted; within each the longest standing first. */
export const rank = (p: Problem, now: number) =>
  (p.muted ? 2 : p.level === 'down' ? 0 : 1) * 1e11 + (p.since ?? now)

/** An incident is about one seat or one switch: a problem on neither can't become one. */
export const canReport = (p: Problem) => !!(p.seat || p.switch_id)

/** What POST /api/incidents takes for a problem, linked back to it (issue #882). */
export const reportBody = (p: Problem) => ({
  ...(p.seat ? { seat: p.seat } : { switch_id: p.switch_id }), title: p.title, from_problem: p.id,
})
