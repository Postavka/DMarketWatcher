import { useState, type FormEvent } from 'react'
import { ApiError, api, type ShortlistResult } from '../lib/api'
import { CandidateCard } from './CandidateCard'

interface Props {
  jobId: string
  aiEnabled: boolean
}

export function ShortlistPanel({ jobId, aiEnabled }: Props) {
  const [request, setRequest] = useState('')
  const [maxPicks, setMaxPicks] = useState(10)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ShortlistResult | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      setResult(await api.shortlist(jobId, { request: request.trim(), max_picks: maxPicks }))
    } catch (e) {
      setResult(null)
      setError(e instanceof ApiError ? e.message : 'Не вдалось зв’язатися з сервером.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel" aria-label="AI-добір">
      <h2>AI-добір</h2>
      <p className="muted">
        Claude перегляне знайдені скіни разом із картинками й залишить ті, що найкраще пасують до вашого опису.
      </p>
      {!aiEnabled && (
        <p className="notice" role="note">
          AI вимкнено: додайте <code>ANTHROPIC_API_KEY</code> у файл <code>.env</code> і перезапустіть сервер.
        </p>
      )}
      <form onSubmit={submit} className="form">
        <label className="field">
          Що саме ви хочете?
          <textarea
            value={request}
            onChange={(e) => setRequest(e.target.value)}
            rows={3}
            maxLength={1000}
            placeholder="Наприклад: яскравий синій сет без мультяшних скінів, щоб гармоніював із моїм ножем"
            disabled={!aiEnabled}
          />
        </label>
        <div className="actions">
          <label className="field inline">
            Скільки показати
            <select value={maxPicks} onChange={(e) => setMaxPicks(Number(e.target.value))} disabled={!aiEnabled}>
              {[5, 10, 15, 20].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="primary" disabled={!aiEnabled || busy || request.trim() === ''}>
            {busy ? 'Claude думає…' : 'Вибрати найкращі'}
          </button>
        </div>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <>
          <h3>Вибір Claude: {result.picks.length}</h3>
          {result.picks.length === 0 ? (
            <p className="empty">Жоден із кандидатів, на думку моделі, не підходить під цей опис.</p>
          ) : (
            <ul className="grid">
              {result.picks.map((p) => (
                <CandidateCard key={p.candidate.offer_id} candidate={p.candidate} reason={p.reason} />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
