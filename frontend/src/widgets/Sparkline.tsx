import { sparkPoints } from './spark'

export function Sparkline({ points, min, max }: { points: number[]; min?: number; max?: number }) {
  return (
    <svg className="fb-spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
      <polyline fill="none" stroke="currentColor" strokeWidth={1.5} vectorEffect="non-scaling-stroke" points={sparkPoints(points, min, max)} />
    </svg>
  )
}
