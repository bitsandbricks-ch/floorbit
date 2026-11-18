import { ActionIcon, Group, Text, Tooltip } from '@mantine/core'
import { IconChevronLeft, IconChevronRight, IconPlayerPause, IconPlayerPlay } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useReducer } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { ErrorBanner } from '@/components/ui'
import { useIdle } from '@/pages/plan/idle'
import { useReloadOnUpdate } from '@/pages/plan/update'
import './screen.css'

export interface ScreenSetup {
  views: { id: string; url: string }[]
  every: number
  qr: { url: string; image: string } | null
}

interface Turn { at: number; reached: number; paused: boolean }
const WAKE = ['pointermove', 'pointerdown', 'wheel'] as const

/** The views are pages of their own: a mouse moved over one, or a key pressed in it, reaches this
 *  page only if passed on, so the controls wake up and the arrow keys work over every view. */
function passOn(frame: HTMLIFrameElement) {
  try {
    const inner = frame.contentWindow
    if (!inner) return
    for (const name of WAKE) inner.addEventListener(name, () => window.dispatchEvent(new Event(name)), { passive: true })
    inner.addEventListener('keydown', (e) => window.dispatchEvent(new KeyboardEvent('keydown', { key: e.key })))
  } catch { /* another origin: the controls wake over the edges only */ }
}

type Step = { to: 'next' | 'prev'; count: number } | { to: 'pause' }

function turn(state: Turn, step: Step): Turn {
  if (step.to === 'pause') return { ...state, paused: !state.paused }
  if (step.count < 2) return state
  const at = (state.at + (step.to === 'next' ? 1 : step.count - 1)) % step.count
  return { ...state, at, reached: Math.max(state.reached, at) }
}

/** ``/screen``: the big screen in the hall, one view at a time with a QR code to the seat finder
 *  (docs/kiosk.md). A view loads one turn before it is shown and stays loaded afterwards, so it
 *  keeps its live updates. Moving the mouse shows which view is on, with buttons to step through. */
export default function BigScreen() {
  const { t, i18n } = useTranslation()
  const { search } = useLocation()
  const q = useQuery({ queryKey: qk.screen(search), queryFn: () => get<ScreenSetup>(`/api/screen${search}`) })
  const views = q.data?.views ?? []
  const count = views.length
  const [state, step] = useReducer(turn, { at: 0, reached: 0, paused: false })
  const idle = useIdle(3000)
  useReloadOnUpdate(true)
  const every = (q.data?.every ?? 30) * 1000

  useEffect(() => {
    if (count < 2 || state.paused) return
    const timer = window.setInterval(() => step({ to: 'next', count }), every)
    return () => window.clearInterval(timer)
    // A step by hand starts the count again: state.at is in the list for that.
  }, [count, every, state.paused, state.at])

  const onKey = useCallback((e: KeyboardEvent) => {
    if (e.key === 'ArrowRight') step({ to: 'next', count })
    else if (e.key === 'ArrowLeft') step({ to: 'prev', count })
    else if (e.key === ' ') step({ to: 'pause' })
  }, [count])
  useEffect(() => {
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onKey])

  if (q.error) return <div className="fb-screen fb-screen--error"><ErrorBanner error={q.error} onRetry={() => q.refetch()} /></div>
  // The QR card says it in the screen's language and the other one: a hall full of guests reads both.
  const other = i18n.getFixedT(i18n.language.startsWith('de') ? 'en' : 'de-CH')
  const name = (id: string) => t(`screen.views.${id}`, { defaultValue: id })
  return (
    <div className={`fb-screen${idle ? ' fb-screen--idle' : ''}`}>
      {views.map((v, i) => (
        <iframe key={v.id + i} className={`fb-screen-view${i === state.at ? ' is-on' : ''}`} title={name(v.id)}
                src={i <= state.reached + 1 ? v.url : undefined}
                aria-hidden={i !== state.at} tabIndex={i === state.at ? 0 : -1}
                onLoad={(e) => passOn(e.currentTarget)} />
      ))}
      {q.data?.qr && (
        <aside className="fb-screen-qr" aria-label={t('screen.find')}>
          <img src={q.data.qr.image} alt={t('screen.qrAlt', { url: q.data.qr.url })} />
          <div>{t('screen.find')}<small>{other('screen.find')}</small><small>{q.data.qr.url}</small></div>
        </aside>
      )}
      {count > 1 && (
        <Group className="fb-screen-controls" gap={6} wrap="nowrap">
          <Tooltip label={t('screen.prev')}><ActionIcon variant="default" size="lg" aria-label={t('screen.prev')}
            onClick={() => step({ to: 'prev', count })}><IconChevronLeft size={18} /></ActionIcon></Tooltip>
          <Text fw={600} px={6} aria-live="polite">{t('screen.position', { name: name(views[state.at]?.id ?? ''), n: state.at + 1, count })}</Text>
          <Tooltip label={state.paused ? t('screen.play') : t('screen.pause')}><ActionIcon variant="default" size="lg"
            aria-label={state.paused ? t('screen.play') : t('screen.pause')} aria-pressed={state.paused}
            onClick={() => step({ to: 'pause' })}>{state.paused ? <IconPlayerPlay size={18} /> : <IconPlayerPause size={18} />}</ActionIcon></Tooltip>
          <Tooltip label={t('screen.next')}><ActionIcon variant="default" size="lg" aria-label={t('screen.next')}
            onClick={() => step({ to: 'next', count })}><IconChevronRight size={18} /></ActionIcon></Tooltip>
        </Group>
      )}
      {count > 1 && !state.paused && (
        <div key={state.at} className="fb-screen-progress" style={{ animationDuration: `${every}ms` }} />
      )}
    </div>
  )
}
