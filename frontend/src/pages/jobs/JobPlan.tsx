import type { Job } from '@/api/types'

/** The job's hall with its seat marked, and a straight line from where the tech is. */
export function JobPlan({ job, label, you }: { job: Job; label: string; you: string }) {
  const d = job.drawing
  if (!d || !job.target) return null
  const [tx, ty] = job.target
  return (
    <svg viewBox={d.box} role="img" aria-label={label} className="fb-job-plan">
      {d.shapes.map((b, i) => (
        <g key={i}>
          <g transform={`translate(${b.cx} ${b.cy}) rotate(${b.rotation})`}>
            {b.cells.map((c) => (
              <rect key={c.seat} className={c.seat === job.seat ? 'cell hit' : 'cell'} x={c.x + 1} y={c.y + 1}
                width={d.cell - 2} height={d.cell - 2} rx={3} />
            ))}
          </g>
          {b.name && <text className="name" x={b.cx} y={b.cy - Math.max(b.w, b.h) / 2 - 18}>{b.name}</text>}
        </g>
      ))}
      {job.from && <line className="route" x1={job.from[0]} y1={job.from[1]} x2={tx} y2={ty} />}
      <circle className="target" cx={tx} cy={ty} r={d.cell * 1.1} />
      {job.from && (
        <g>
          <circle className="you" cx={job.from[0]} cy={job.from[1]} r={d.cell * 0.55} />
          <text className="you-label" x={job.from[0]} y={job.from[1] - d.cell}>{you}</text>
        </g>
      )}
    </svg>
  )
}
