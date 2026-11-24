import type {
  DnsResolver, GameServer, GameServerList, InternetSite, IspUplink, ServiceStatus, Services as ServicesData,
} from '@/api/types'
import type { OwnCheck } from '@/api/serviceChecks'
import { bps } from '@/pages/stats/format'
import { bytes } from '@/pages/traffic/format'

/** Every kind of service, in the order the page groups them. The LAN cache, DHCP and firewalls come
 *  from their log, plugin or page, so nobody adds one here; ``check`` is the crew's own (#1338). */
export const TYPES = ['uplink', 'dns', 'site', 'lancache', 'dhcp', 'firewall', 'game', 'check', 'other'] as const
export type ServiceType = typeof TYPES[number]
export const STATES: ServiceStatus[] = ['down', 'warn', 'unknown', 'up']

/** One row of the list, whatever kind of service it is. */
export interface ServiceRowData {
  /** ``sid``: its id in the summary and on the health wall (``uplink:<id>``), for tags and mutes. */
  key: string; sid: string; type: ServiceType; name: string; status: ServiceStatus; target: string
  value: string | null; unit: string | null; note: string | null; points: number[]
  edit?: () => void; game?: GameServer; tags?: string[]
  /** Set up somewhere else (a plugin, Network > Firewalls): where, in words. */
  elsewhere?: string
}

type T = (key: string, opts?: Record<string, unknown>) => string

/** The page's rows from the two lists: the headline number, a line under it and the sparkline. */
export function serviceRows(t: T, d: ServicesData | undefined, g: GameServerList | undefined, edit: {
  uplink?: (u: IspUplink) => void; dns?: (r: DnsResolver) => void; site?: (s: InternetSite) => void; game?: (s: GameServer) => void
  check?: (c: OwnCheck) => void
}): ServiceRowData[] {
  const failed = (status: ServiceStatus, error: string) => (status === 'down' || status === 'unknown' ? error || t('services.notChecked') : null)
  const rows: ServiceRowData[] = []
  for (const u of d?.uplinks ?? []) {
    const portDown = u.port_state === 'down' || u.port_state === 'disabled'
    const used = portDown ? null : u.utilization ?? null
    rows.push({
      key: `u-${u.id}`, sid: `uplink:${u.id}`, type: 'uplink', name: u.name, status: u.status, target: `${u.device} ${u.port} · ${bps(u.capacity_mbps * 1e6)}`,
      value: used != null ? `${Math.round(used * 100)}%` : null, unit: used != null ? t('services.used') : null,
      note: portDown ? t('services.portDown') : [
        used != null && t('services.inOut', { in: bps(u.in_bps), out: bps(u.out_bps) }),
        u.latency_ms != null && t('services.latency', { ms: u.latency_ms }),
        u.loss != null && t('services.loss', { pct: Math.round(u.loss * 100) }),
      ].filter(Boolean).join(' · ') || u.error || null,
      points: u.history.map(([, ms]) => ms ?? 0), edit: edit.uplink && (() => edit.uplink!(u)),
    })
  }
  for (const r of d?.resolvers ?? []) {
    const ok = r.status === 'up' || r.status === 'warn'
    rows.push({
      key: `r-${r.id}`, sid: `dns:${r.id}`, type: 'dns', name: r.name, status: r.status, target: `${r.address} · ${r.lookup}`,
      value: ok ? `${r.latency_ms} ms` : null, unit: null,
      note: ok ? t('services.answers', { count: r.answers ?? 0 }) : failed(r.status, r.error),
      points: r.history.map(([, ms]) => ms ?? 0), edit: edit.dns && (() => edit.dns!(r)),
    })
  }
  for (const s of d?.sites ?? []) {
    const ok = s.status === 'up' || s.status === 'warn'
    rows.push({
      key: `s-${s.id}`, sid: `site:${s.id}`, type: 'site', name: s.name, status: s.status, target: s.port === 443 ? s.host : `${s.host}:${s.port}`,
      value: ok ? `${s.latency_ms} ms` : null, unit: null,
      note: ok ? (s.loss ? t('services.loss', { pct: Math.round(s.loss * 100) }) : null) : failed(s.status, s.error),
      points: s.history.map(([, ms]) => ms ?? 0), edit: edit.site && (() => edit.site!(s)),
    })
  }
  for (const oc of d?.checks ?? []) {
    const ok = oc.status === 'up' || oc.status === 'warn'
    rows.push({
      key: `c-${oc.id}`, sid: `check:${oc.id}`, type: 'check', name: oc.name, status: oc.status, target: checkTarget(t, oc),
      value: ok && oc.latency_ms != null ? `${oc.latency_ms} ms` : null, unit: null,
      note: ok ? [oc.code != null && t('services.check.code', { code: oc.code }),
        oc.loss ? t('services.loss', { pct: Math.round(oc.loss * 100) }) : null,
        oc.cert_days != null && t('services.check.certDays', { count: oc.cert_days }), oc.note].filter(Boolean).join(' · ') || null
        : failed(oc.status, oc.error),
      points: oc.history.map(([, ms]) => ms ?? 0), edit: edit.check && (() => edit.check!(oc)),
    })
  }
  const c = d?.lan_cache
  if (c) {
    rows.push({
      key: 'lancache', sid: 'lancache', type: 'lancache', name: t('services.lanCache'), status: c.status, target: c.demo ? t('services.demo') : t('services.thisHour'),
      value: c.hit_ratio != null ? `${Math.round(c.hit_ratio * 100)}%` : null, unit: t('services.fromDisk'),
      note: [t('services.served', { bytes: bytes(c.served_bytes), rate: bps(c.bps) }),
        c.disk && t('services.diskUsed', { used: bytes(c.disk.used), total: bytes(c.disk.total) }), c.error].filter(Boolean).join(' · '),
      points: [],
    })
  }
  for (const s of g?.servers ?? []) {
    const info = s.status === 'up' ? s.info : null
    rows.push({
      key: `g-${s.id}`, sid: `game:${s.id}`, type: 'game', name: s.name, status: s.status, target: [s.game || s.info?.game, `${s.host}:${s.port}`].filter(Boolean).join(' · '),
      value: info && s.query !== 'tcp' ? `${info.players}/${info.max_players}` : null, unit: info && s.query !== 'tcp' ? t('gameServers.players') : null,
      note: info ? [info.map && t('gameServers.map', { map: info.map }), info.ping_ms != null && `${info.ping_ms} ms`, info.version].filter(Boolean).join(' · ')
        : s.error || t('gameServers.notAsked'),
      points: s.query !== 'tcp' ? s.history.map(([, n]) => n ?? 0) : [], edit: edit.game && (() => edit.game!(s)), game: s,
    })
  }
  return rows
}


/** "Ping · 192.0.2.40", "TCP · host:8080", "HTTP(S) · https://..." */
export function checkTarget(t: T, c: Pick<OwnCheck, 'kind' | 'host' | 'port' | 'url'>): string {
  const where = c.kind === 'http' ? c.url : c.port ? `${c.host}:${c.port}` : c.host
  return `${t(`services.check.kinds.${c.kind}`)} · ${where}`
}

/** Which group a summary row's kind (floorbit/health.py KINDS) goes in. */
const FROM_KIND: Record<string, ServiceType> = {
  uplink: 'uplink', dns: 'dns', web: 'site', cache: 'lancache', dhcp: 'dhcp', firewall: 'firewall', game: 'game',
  check: 'check', other: 'other',
}
export const typeOfKind = (kind: string): ServiceType => FROM_KIND[kind] ?? 'other'
