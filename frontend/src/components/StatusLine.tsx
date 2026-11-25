import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan, useProblems } from '@/api/queries'
import { ago } from '@/lib/time'
import { Attribution } from './Attribution'

/** One quiet line under every crew page: how the network is, how many agents answer, when it
 *  was last checked, then the attribution and the version. ``bare`` inside the shared shell,
 *  whose own footer holds it; a dashboard screen draws it on its own. */
export function StatusLine({ bare = false }: { bare?: boolean }) {
  const { t } = useTranslation()
  const problems = useProblems().data
  const admin = useCan('settings.manage')
  // The agents' list is for those who manage settings; the sidebar asks nobody else.
  const agents = useQuery({
    queryKey: qk.agents, queryFn: () => get<{ agents: { connected: boolean }[] }>('/api/agents'),
    enabled: admin, refetchInterval: 30_000, retry: false,
  }).data?.agents
  const down = problems?.counts.down ?? 0
  const warn = problems?.counts.look ?? problems?.counts.warn ?? 0
  return (
    <Frame bare={bare} label={t('nav.statusLine')}>
      {problems && (
        <Link to="/problems" className="fb-status-item">
          <span className={`fb-bit${down ? ' is-down' : warn ? ' is-warn' : ''}`} aria-hidden="true" />
          {down || warn ? t('nav.status.problems', { down, warn }) : t('nav.status.allUp')}
        </Link>
      )}
      {agents && agents.length > 0 && (
        <Link to="/settings/agents" className="fb-status-item">
          {t('nav.status.agents', { online: agents.filter((a) => a.connected).length, total: agents.length })}
        </Link>
      )}
      {problems && <span className="fb-status-item fb-status-when">{t('nav.status.checked', { ago: ago(problems.checked_at) })}</span>}
      <span className="fb-status-grow" />
      <Attribution compact version />
    </Frame>
  )
}

function Frame({ bare, label, children }: { bare: boolean; label: string; children: ReactNode }) {
  if (bare) return <div className="fb-status">{children}</div>
  return <footer className="fb-status fb-status-own" aria-label={label}>{children}</footer>
}
