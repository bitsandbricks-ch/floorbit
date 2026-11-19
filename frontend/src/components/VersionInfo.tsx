import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { dateOnly, dateTime } from '@/lib/time'

/** What GET /api/version says about this server (floorbit/build_info.py). */
export interface BuildInfo {
  app: string
  release?: string | null
  commit?: string | null
  built?: number | null
  source?: string
  dev?: boolean
  /** Only for those who manage settings: the connected local agents. */
  agents?: { name: string; version: string | null }[]
}

const SHORT = 7

/** One small line under the attribution: which Floorbit runs here, from which commit, built when,
 *  and the agents' versions. For telling at a glance whether an update reached this server. */
export function VersionInfo() {
  const { t } = useTranslation()
  const q = useQuery({ queryKey: qk.version, queryFn: () => get<BuildInfo>('/api/version'), staleTime: 5 * 60_000, retry: false })
  const b = q.data
  if (!b?.app) return null
  const source = b.source || 'https://github.com/bitsandbricks-ch/floorbit'
  const agents = (b.agents ?? []).filter((a) => a.version)
  return (
    <div className="fb-version" data-testid="version-info">
      {b.release ? (
        <a href={`${source}/releases/tag/v${b.release}`} target="_blank" rel="noopener noreferrer">
          {t('version.release', { version: b.release })}
        </a>
      ) : (
        <span>{t('version.release', { version: b.app })}</span>
      )}
      {b.dev && <span className="fb-version-dev">{t('version.dev')}</span>}
      {b.commit && (
        <a href={`${source}/commit/${b.commit}`} target="_blank" rel="noopener noreferrer"
          title={t('version.commitTitle', { commit: b.commit })} className="fb-version-hash">
          {b.commit.slice(0, SHORT)}
        </a>
      )}
      {b.built ? (
        <span title={dateTime(b.built)}>{t('version.built', { date: dateOnly(b.built, undefined, { dateStyle: 'medium' }) })}</span>
      ) : null}
      {agents.length > 0 && (
        <span>
          {agents.length === 1
            ? t('version.agent', { version: agents[0].version })
            : t('version.agents', { list: agents.map((a) => `${a.name} ${a.version}`).join(', ') })}
        </span>
      )}
    </div>
  )
}
