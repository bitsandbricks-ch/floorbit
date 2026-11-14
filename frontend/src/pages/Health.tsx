import { Alert, Anchor, Button, Group, Loader, Text } from '@mantine/core'
import { IconMaximize, IconRefresh } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type CSSProperties, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan, useHealth } from '@/api/queries'
import type { HealthCheck, HealthKind, HealthWall, State } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

const KINDS: HealthKind[] = ['dhcp', 'dns', 'cache', 'game', 'uplink', 'web', 'other']
const STATES: State[] = ['down', 'warn', 'up', 'unknown']

/** Seconds since a unix time, ticking once every few seconds. */
function useAge(since: number | null | undefined) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 5000)
    return () => window.clearInterval(id)
  }, [])
  return since ? Math.max(0, Math.round(now / 1000 - since)) : null
}

function Ago({ since }: { since: number }) {
  const { t } = useTranslation()
  const age = useAge(since) ?? 0
  return <>{age < 60 ? t('health.agoSeconds', { count: age }) : t('health.agoMinutes', { count: Math.floor(age / 60) })}</>
}

function Tile({ check }: { check: HealthCheck }) {
  const { t } = useTranslation()
  return (
    <article className={`fb-health-tile ${check.status}`} aria-label={`${check.name}: ${t(`health.status.${check.status}`)}`}>
      <header>
        <span className={`fb-dot ${check.status}`} aria-hidden="true" />
        <strong>{check.link ? <Anchor href={check.link} c="inherit" fw="inherit">{check.name}</Anchor> : check.name}</strong>
        <span className="fb-health-state">{t(`health.status.${check.status}`)}</span>
      </header>
      {check.summary && <p className="fb-health-summary">{check.summary}</p>}
      {check.metrics.length > 0 && (
        <dl className="fb-health-metrics">
          {check.metrics.map((m) => (
            <div key={m.label}>
              <dt>{m.label}</dt>
              <dd className={m.tone ? `fb-tone-${m.tone}` : undefined}>
                {m.value}
                {m.unit && <small> {m.unit}</small>}
              </dd>
            </div>
          ))}
        </dl>
      )}
      <footer>
        {t('health.since')} <Ago since={check.since} />
      </footer>
    </article>
  )
}

function Wall({ wall }: { wall: HealthWall }) {
  const { t } = useTranslation()
  if (!wall.checks.length) {
    return <Text c="dimmed">{wall.plugins ? t('health.noChecks') : t('health.noPlugins')}</Text>
  }
  return (
    <>
      <p className="fb-health-counts" aria-live="polite">
        {STATES.filter((s) => wall.counts[s]).map((s) => (
          <span key={s} className={`fb-health-count ${s}`}>
            <span className={`fb-dot ${s}`} aria-hidden="true" />
            {t(`health.count.${s}`, { count: wall.counts[s] })}
          </span>
        ))}
      </p>
      <div className="fb-health-groups">
      {KINDS.map((kind) => {
        const checks = wall.checks.filter((c) => c.kind === kind)
        if (!checks.length) return null
        return (
          <section key={kind} className="fb-health-group" aria-labelledby={`health-${kind}`}>
            <h2 id={`health-${kind}`}>{t(`health.kind.${kind}`)}</h2>
            <div className="fb-health-grid" style={{ '--n': Math.min(checks.length, 3) } as CSSProperties}>
              {checks.map((c) => <Tile key={c.id} check={c} />)}
            </div>
          </section>
        )
      })}
      </div>
    </>
  )
}

/** The service health wall: DHCP, DNS, the LAN cache, game servers and the uplink at a glance.
 *  ``?screen=1`` drops the header for a kiosk or ops screen (``?theme=`` picks its look). */
export default function Health() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const health = useHealth()
  const canCheck = useCan('plugins.run')
  const screen = new URLSearchParams(window.location.search).get('screen') === '1'
  const lastAge = useAge(health.data?.last_poll)
  useLiveEvent('health.changed', () => void client.invalidateQueries({ queryKey: qk.health }))
  const check = useMutation({
    mutationFn: () => post<HealthWall>('/api/health/check'),
    onSuccess: (data) => client.setQueryData(qk.health, data),
  })
  const error = health.error ?? check.error

  const body = (
    <>
      {error && (
        <Alert color="down" role="alert" mb="md">
          {t('common.error', { message: error.message })}
        </Alert>
      )}
      {health.isPending ? <Loader size="sm" /> : health.data && <Wall wall={health.data} />}
    </>
  )

  if (screen) {
    return (
      <main className="fb-health-screen">
        <header>
          <h1>{t('health.title')}</h1>
          {lastAge !== null && <span>{t('health.checked', { count: lastAge })}</span>}
        </header>
        {body}
      </main>
    )
  }
  return (
    <Layout title={t('health.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead
        title={t('health.title')}
        desc={t('health.intro')}
        actions={
          <Group gap="xs">
            <Button variant="default" component="a" href="/health?screen=1" leftSection={<IconMaximize size={16} />}>
              {t('health.screen')}
            </Button>
            {canCheck && (
              <Button leftSection={<IconRefresh size={16} />} loading={check.isPending} onClick={() => check.mutate()}>
                {t('health.checkNow')}
              </Button>
            )}
          </Group>
        }
      />
      {lastAge !== null && (
        <Text size="sm" c="dimmed" mb="sm">
          {t('health.checked', { count: lastAge })}
        </Text>
      )}
      {body}
    </Layout>
  )
}
