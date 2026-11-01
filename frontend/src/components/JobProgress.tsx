import type { Job } from '../lib/api'
import { STAGE_LABELS } from '../lib/format'

export function JobProgress({ job }: { job: Job | null }) {
  const label = job?.stage ? (STAGE_LABELS[job.stage] ?? job.stage) : 'Запуск пошуку'
  const known = job !== null && job.total > 0
  const percent = known ? Math.round((job.done / job.total) * 100) : 0
  return (
    <div className="panel progress" role="status" aria-live="polite">
      <p>
        {label}
        {known ? ` — ${job.done} з ${job.total}` : '…'}
      </p>
      <div className={`bar ${known ? '' : 'indeterminate'}`}>
        <span style={known ? { width: `${percent}%` } : undefined} />
      </div>
      <p className="hint">Перший пошук може тривати до пари хвилин, наступні майже миттєві (дані кешуються).</p>
    </div>
  )
}
