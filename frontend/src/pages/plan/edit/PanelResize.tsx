import { useTranslation } from 'react-i18next'
import { PANEL_MAX, PANEL_MIN } from './panelWidth'
import './PanelResize.css'

/** The panel's left edge: drag it to make the panel wider or narrower (Mike: the panel was crammed),
 *  double-click to go back to the default width. Arrow keys work too. */
export function PanelResize({ width, onWidth }: { width: number | null; onWidth: (w: number | null) => void }) {
  const { t } = useTranslation()
  const clamp = (w: number) => Math.round(Math.min(PANEL_MAX, Math.max(PANEL_MIN, w)))
  const current = (el: Element) => width ?? el.parentElement?.getBoundingClientRect().width ?? 440
  const start = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    e.preventDefault()
    const el = e.currentTarget
    el.setPointerCapture?.(e.pointerId)
    const x0 = e.clientX, w0 = current(el)
    const move = (ev: PointerEvent) => onWidth(clamp(w0 + (x0 - ev.clientX)))
    const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); el.removeEventListener('pointercancel', up) }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
    el.addEventListener('pointercancel', up)
  }
  return (
    <div className="fb-panel-resize" role="separator" aria-orientation="vertical" aria-label={t('editPanel.resize')} tabIndex={0}
      aria-valuemin={PANEL_MIN} aria-valuemax={PANEL_MAX} aria-valuenow={width ?? undefined}
      onPointerDown={start} onDoubleClick={() => onWidth(null)}
      onKeyDown={(e) => {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
        e.preventDefault()
        onWidth(clamp(current(e.currentTarget) + (e.key === 'ArrowLeft' ? 20 : -20)))
      }} />
  )
}
