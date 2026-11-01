import { useCallback, useEffect, useRef, useState } from 'react'
import { JobProgress } from './components/JobProgress'
import { Results } from './components/Results'
import { SearchForm } from './components/SearchForm'
import { ShortlistPanel } from './components/ShortlistPanel'
import { ApiError, api, waitForJob, type Health, type Job, type SearchParams, type Side } from './lib/api'
import { orderCategories } from './lib/format'

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [categories, setCategories] = useState<string[]>([])
  const [job, setJob] = useState<Job | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const loadSlots = useCallback((side: Side) => {
    api
      .slots(side)
      .then((slots) => setCategories(orderCategories([...new Set(slots.map((s) => s.category))])))
      .catch(() => setCategories([]))
  }, [])

  useEffect(() => {
    api.health().then(setHealth).catch(() => setError('Сервер недоступний. Запустіть бекенд (uvicorn) і оновіть сторінку.'))
    loadSlots('ct')
    return () => abortRef.current?.abort()
  }, [loadSlots])

  async function search(params: SearchParams) {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setBusy(true)
    setError(null)
    setJob(null)
    try {
      const { job_id } = await api.startSearch(params)
      const finished = await waitForJob(job_id, setJob, { signal: controller.signal })
      setJob(finished)
    } catch (e) {
      if (controller.signal.aborted) return
      setJob(null)
      setError(e instanceof ApiError || e instanceof Error ? e.message : 'Невідома помилка')
    } finally {
      if (abortRef.current === controller) setBusy(false)
    }
  }

  const finished = job?.status === 'done' && job.candidates !== null

  return (
    <main>
      <header className="app-head">
        <h1>DMarket Watcher</h1>
        <p className="muted">Підбір скінів CS2 за кольором і бюджетом. Лише перегляд: нічого не купується.</p>
        {health && health.catalog_skins === 0 && (
          <p className="notice">Каталог скінів ще порожній. Виконайте <code>scripts/load_catalog.py</code>.</p>
        )}
      </header>

      <SearchForm categories={categories} busy={busy} onSideChange={loadSlots} onSubmit={search} />

      {error && (
        <p className="error panel" role="alert">
          {error}
        </p>
      )}
      {busy && <JobProgress job={job} />}
      {finished && job && (
        <>
          <Results candidates={job.candidates ?? []} stats={job.stats} />
          {(job.candidates?.length ?? 0) > 0 && <ShortlistPanel jobId={job.id} aiEnabled={health?.ai_enabled ?? false} />}
        </>
      )}
    </main>
  )
}
