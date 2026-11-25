import { Group, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { clock, dayClock } from '@/lib/time'
import './LogVolume.css'

/** One slice of the chart, as /api/logs/volume answers: start (unix seconds), lines, errors. */
export type VolumeBucket = [number, number, number]
export interface LogVolumeData { since: number; until: number; step: number; buckets: VolumeBucket[] }

const span = (s: number) => (s < 60 ? `${s} s` : s < 3600 ? `${Math.round(s / 60)} min` : `${Math.round(s / 3600)} h`)

/** How many lines came in over time, errors in red (issue #1048). Clicking a bar narrows the list
 *  to its slice of time; the keyboard way is the Time filter, so the bars stay out of the tab order. Plain SVG bars: the shared TimeChart draws a line, and a log's
 *  bursts read better as bars. */
export function LogVolume({ data, onZoom }: { data: LogVolumeData; onZoom: (since: number, until: number) => void }) {
  const { t, i18n } = useTranslation()
  const max = Math.max(1, ...data.buckets.map((b) => b[1]))
  const at = (ts: number) => (data.until - data.since >= 86400 ? dayClock : clock)(ts, i18n.language)
  const w = 100 / data.buckets.length
  return (
    <figure className="fb-log-volume" aria-label={t('logVolume.chart')}>
      <div className="fb-log-volume-bars" title={t('logVolume.zoom')}>
        {data.buckets.map(([start, count, errors]) => (
          <button key={start} type="button" className="fb-log-volume-bar" style={{ width: `${w}%` }}
            aria-label={t('logVolume.bar', { time: at(start), count, errors })} disabled={count === 0} tabIndex={-1}
            onClick={() => onZoom(start, Math.min(data.until, start + data.step))}>
            <span className="fb-log-volume-all" style={{ height: count ? `max(2px, ${(count / max) * 100}%)` : 0 }}>
              {errors > 0 && <span className="fb-log-volume-err" style={{ height: `${(errors / count) * 100}%` }} />}
            </span>
          </button>
        ))}
      </div>
      <Group justify="space-between" gap="xs" mt={2} wrap="nowrap">
        <Text size="xs" c="dimmed">{at(data.since)}</Text>
        <Text size="xs" c="dimmed">{t('logVolume.max', { n: max.toLocaleString(i18n.language), step: span(data.step) })}</Text>
        <Text size="xs" c="dimmed">{at(data.until)}</Text>
      </Group>
    </figure>
  )
}
