import { useTranslation } from 'react-i18next'
import type { OverlayContext } from '../SeatMap'
import type { Box, Point } from './geometry'

/** A small padlock at the top right of each locked item that is selected, so it is clear why it
 *  doesn't move or show handles. */
export function LockBadges({ ctx, boxes }: { ctx: OverlayContext; boxes: { box: Box; centre: Point; rotation: number }[] }) {
  const { t } = useTranslation()
  const px = 1 / ctx.scale
  return (
    <g className="fb-edit-lock" pointerEvents="none">
      {boxes.map(({ box, centre, rotation }, i) => (
        <g key={i} transform={`rotate(${rotation} ${centre.x} ${centre.y}) translate(${box.x + box.w} ${box.y}) rotate(${-rotation}) scale(${px})`}>
          <title>{t('plan.edit.locked')}</title>
          <circle r={10} />
          <rect x={-4.5} y={-1.5} width={9} height={7} rx={1.5} />
          <path d="M -2.75 -1.5 V -4 a 2.75 2.75 0 0 1 5.5 0 V -1.5" />
        </g>
      ))}
    </g>
  )
}
