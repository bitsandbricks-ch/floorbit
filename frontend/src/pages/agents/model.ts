import type { TFunction } from 'i18next'
import type { Agent, AgentPluginHealth } from '@/api/types'
import { ago } from '@/lib/time'

export type Tone = 'up' | 'warn' | 'down'
export interface Problem { tone: 'warn' | 'down'; text: string; blocked?: boolean; link?: HintLink }
export interface HintLink { href: string; internal: boolean }

const AGENT_DOCS = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/agent.md'
/** Where each health hint (floorbit/plugins/agent.py, Health.set) sends the tech to fix it. */
const HINT_LINKS: Record<string, HintLink> = {
  telegraf_missing: { href: `${AGENT_DOCS}#telegraf`, internal: false },
  telegraf_stopped: { href: `${AGENT_DOCS}#telegraf`, internal: false },
  telegraf_sidecar_left: { href: `${AGENT_DOCS}#telegraf`, internal: false },
  telegraf_quiet: { href: '/settings/telemetry', internal: true },
  device_problems: { href: '/settings/telemetry', internal: true },
}

/** What a plugin says about itself: the translated sentence for a known hint, else its own words. */
export function pluginSays(p: AgentPluginHealth, t: TFunction): { text: string; detail: string; link?: HintLink } {
  const key = p.hint ? `agents.hint.${p.hint}` : ''
  if (key && t(key, { defaultValue: '' })) {
    // The agent's own words still say which device and why: kept as the detail.
    return { text: t(key), detail: p.message, link: HINT_LINKS[p.hint!] }
  }
  return { text: p.message, detail: '' }
}

/** Version strings compared number by number ("0.10.0" after "0.9.3"); anything else counts low. */
export function compareVersions(a: string, b: string): number {
  const parts = (v: string) => v.replace(/^v/, '').split('.').map((p) => {
    const n = /^\d+/.exec(p)
    return n ? Number(n[0]) : -1
  })
  const x = parts(a), y = parts(b)
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    const d = (x[i] ?? 0) - (y[i] ?? 0)
    if (d) return d
  }
  return 0
}

export function behind(agent: Agent, newest?: string | null): boolean {
  return !!(agent.version && newest && compareVersions(agent.version, newest) < 0)
}

export function plugins(agent: Agent): [string, AgentPluginHealth][] {
  return Object.entries(agent.report?.plugins ?? {}).sort(([a], [b]) => a.localeCompare(b))
}

/** What on one agent needs a look, worst first: the card lists it and the overview counts it. */
export function problems(agent: Agent, newest: string | null | undefined, protocol: number | undefined, t: TFunction, lang: string): Problem[] {
  const out: Problem[] = []
  if (!agent.connected) {
    out.push({ tone: 'down', text: agent.last_seen ? t('agents.problem.offline', { when: ago(agent.last_seen, lang) }) : t('agents.problem.never') })
  }
  for (const [id, p] of plugins(agent)) {
    if (!p.running && p.status !== 'off') out.push({ tone: 'down', text: t('agents.problem.pluginStopped', { plugin: id, message: p.message || '–' }) })
    else if (p.status === 'error') {
      const says = pluginSays(p, t)
      out.push({ tone: 'down', text: t('agents.problem.pluginError', { plugin: id, message: says.text || p.errors[p.errors.length - 1]?.error || '–' }), link: says.link })
    }
    else if (p.status === 'warning') {
      const says = pluginSays(p, t)
      out.push({ tone: 'warn', text: t('agents.problem.pluginWarning', { plugin: id, message: says.text || '–' }), link: says.link })
    }
  }
  for (const [id, p] of plugins(agent)) {
    for (const b of p.auth_blocked ?? []) {
      out.push({ tone: 'down', blocked: true, text: t('agents.problem.blocked', { plugin: id, device: b.device, credential: b.credential }) })
    }
  }
  if (agent.outdated) out.push({ tone: 'warn', text: t('agents.outdatedHelp', { v: protocol ?? '' }) })
  else if (behind(agent, newest)) out.push({ tone: 'warn', text: t('agents.problem.behind', { v: agent.version, newest }) })
  const r = agent.report
  if (r?.syslog_dropped) out.push({ tone: 'warn', text: t('agents.reportSyslogDropped', { count: r.syslog_dropped, n: r.syslog_dropped.toLocaleString(lang) }) })
  if (r?.calls_busy) out.push({ tone: 'warn', text: t('agents.reportBusy', { count: r.calls_busy }) })
  if (agent.stats?.failed) {
    const e = agent.stats.last_error
    out.push({ tone: 'warn', text: e
      ? t('agents.problem.failedLast', { count: agent.stats.failed, method: e.method, error: e.error ?? '?', when: ago(e.at, lang) })
      : t('agents.problem.failed', { count: agent.stats.failed }) })
  }
  return out.sort((a, b) => (a.tone === b.tone ? 0 : a.tone === 'down' ? -1 : 1))
}

export function worst(list: Problem[]): Tone {
  if (list.some((p) => p.tone === 'down')) return 'down'
  return list.length ? 'warn' : 'up'
}

export const PLUGIN_COLOR: Record<AgentPluginHealth['status'], string> = { ok: 'up', warning: 'warn', error: 'down', off: 'gray' }

export function uptime(seconds: number): { key: string; n: number } {
  if (seconds >= 86400) return { key: 'agents.upDays', n: Math.floor(seconds / 86400) }
  if (seconds >= 3600) return { key: 'agents.upHours', n: Math.floor(seconds / 3600) }
  return { key: 'agents.upMinutes', n: Math.max(1, Math.floor(seconds / 60)) }
}

export function stateKey(a: Agent, tone: Tone) {
  return !a.connected ? 'offline' : tone === 'up' ? 'ok' : tone
}

export function upText(t: (k: string, o?: Record<string, unknown>) => string, a: Agent) {
  if (!a.connected || a.report?.up_seconds === undefined) return '–'
  const up = uptime(a.report.up_seconds)
  return t(`agents.duration.${up.key.slice('agents.up'.length).toLowerCase()}`, { count: up.n })
}

