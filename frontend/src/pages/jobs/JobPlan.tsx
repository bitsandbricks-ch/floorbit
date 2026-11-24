import type { Job } from '@/api/types'
import { MiniPlan } from '@/components/MiniPlan'

/** The job's hall with its seat marked, and a straight line from where the tech is. */
export function JobPlan({ job, label, you }: { job: Job; label: string; you: string }) {
  const d = job.drawing
  if (!d || !job.target) return null
  const [tx, ty] = job.target
  return (
    <MiniPlan drawing={d} label={label} className="fb-job-plan" points={job.from ? [job.target, job.from] : [job.target]}
      seat={(id) => (id === job.seat ? { className: 'hit' } : undefined)}>
      {job.from && <line className="route" x1={job.from[0]} y1={job.from[1]} x2={tx} y2={ty} />}
      <circle className="target" cx={tx} cy={ty} r={d.cell * 1.1} />
      {job.from && (
        <g>
          <circle className="you" cx={job.from[0]} cy={job.from[1]} r={d.cell * 0.55} />
          <text className="you-label" x={job.from[0]} y={job.from[1] - d.cell}>{you}</text>
        </g>
      )}
    </MiniPlan>
  )
}
