import { Button, Group, Text } from '@mantine/core'
import { IconBellCog } from '@tabler/icons-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useMe, useProblems } from '@/api/queries'
import type { Problem } from '@/api/types'
import { ago } from '@/lib/time'
import { inApp } from '@/nav/sections'
import { NotifySettings } from './NotifySettings'
import { SidePanel } from './SidePanel'

/** The bell's drawer: what needs a look right now, newest first, each leading to its page. */
export function Notifications({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const me = useMe().data
  const q = useProblems()
  const [settings, setSettings] = useState(false)
  const list: Problem[] = [...(q.data?.problems ?? []), ...(q.data?.attention ?? [])]
    .filter((p) => !p.muted)
    .sort((a, b) => (a.level === b.level ? (b.since ?? 0) - (a.since ?? 0) : a.level === 'down' ? -1 : 1))
  return (
    <>
      <SidePanel
        opened={opened} onClose={onClose} title={t('nav.notifications')} size={400}
        kicker={q.data ? t('nav.notify.checked', { ago: ago(q.data.checked_at) }) : undefined}
        href="/problems" openLabel={t('nav.notify.all')}
        actions={me?.user && (
          <Button size="xs" variant="default" leftSection={<IconBellCog size={14} aria-hidden="true" />} onClick={() => setSettings(true)}>
            {t('nav.notify.settings')}
          </Button>
        )}
      >
        {list.length === 0 && (
          <Group gap={10} className="fb-notify-empty">
            <span className="fb-bit" aria-hidden="true" />
            <Text size="sm" c="dimmed">{q.isPending ? t('common.loading') : t('nav.notify.empty')}</Text>
          </Group>
        )}
        <ul className="fb-notify-list">
          {list.map((p) => (
            <li key={p.id}>
              <Row href={p.link} onClick={onClose}>
                <span className={`fb-bit is-${p.level}`} aria-hidden="true" />
                <span className="fb-notify-text">
                  <b>{p.title}</b>
                  {p.where && <small>{p.where}</small>}
                </span>
                {p.since ? <time className="fb-notify-when">{ago(p.since)}</time> : null}
              </Row>
            </li>
          ))}
        </ul>
      </SidePanel>
      {settings && <NotifySettings opened onClose={() => setSettings(false)} />}
    </>
  )
}

// A problem's link may be a page Flask draws (``/`` opens the plan with a switch picked): a plain link then.
function Row({ href, onClick, children }: { href: string; onClick: () => void; children: ReactNode }) {
  if (!inApp(href)) return <a href={href} className="fb-notify-row">{children}</a>
  return <Link to={href} className="fb-notify-row" onClick={onClick}>{children}</Link>
}
