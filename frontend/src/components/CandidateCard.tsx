import type { Candidate } from '../lib/api'
import { money } from '../lib/format'

interface Props {
  candidate: Candidate
  reason?: string
}

export function CandidateCard({ candidate: c, reason }: Props) {
  return (
    <li className="card">
      <img src={c.image} alt={c.skin} loading="lazy" width={256} height={192} />
      <div className="card-body">
        <h3>{c.skin}</h3>
        <p className="muted">
          {c.wear || 'Без зносу'}
          {c.collection ? ` · ${c.collection}` : ''}
        </p>
        <p className="price">{money(c.price_cents)}</p>
        <p className="muted small">
          {c.float_value !== null ? `float ${c.float_value.toFixed(4)}` : 'без float'}
          {c.paint_seed !== null ? ` · seed ${c.paint_seed}` : ''}
        </p>
        <div
          className="meter"
          role="img"
          aria-label={`Покриття кольором: ${Math.round(c.coverage * 100)}%`}
          title={`Покриття кольором: ${Math.round(c.coverage * 100)}%`}
        >
          <span style={{ width: `${Math.min(100, Math.round(c.coverage * 100))}%` }} />
        </div>
        {reason && <p className="reason">{reason}</p>}
      </div>
    </li>
  )
}
