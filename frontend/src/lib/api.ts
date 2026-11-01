export type Side = 'ct' | 't'

export interface SearchParams {
  side: Side
  colors: string[]
  budget_cents: number | null
  categories: string[]
  weapons: string[]
  wears: string[]
  stattrak: boolean
  per_weapon: number | null
  limit: number
}

export interface Candidate {
  skin: string
  weapon: string
  category: string
  offer_id: string
  title: string
  wear: string
  price_cents: number
  float_value: number | null
  paint_seed: number | null
  image: string
  collection: string
  rarity: string
  coverage: number
  dominance: number
}

export interface SelectionStats {
  skins_in_scope: number
  without_color_profile: number
  color_matched: number
  titles_requested: number
  hydrate_failed: number
  with_offers_in_budget: number
}

export interface Job {
  id: string
  status: 'running' | 'done' | 'failed'
  stage: string
  done: number
  total: number
  error: string | null
  candidates: Candidate[] | null
  stats: SelectionStats | null
}

export interface Pick {
  candidate: Candidate
  reason: string
}

export interface ShortlistResult {
  picks: Pick[]
  ignored: string[]
  input_tokens: number
  output_tokens: number
}

export interface Health {
  status: string
  catalog_skins: number
  ai_enabled: boolean
}

export interface Slot {
  category: string
  weapon: string
  skins: number
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch {
      /* keep the status text */
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

export const api = {
  health: () => request<Health>('/api/health'),
  slots: (side: Side) => request<Slot[]>(`/api/catalog/slots?side=${side}`),
  startSearch: (params: SearchParams) =>
    request<{ job_id: string }>('/api/modes/color-build/search', post(params)),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  shortlist: (jobId: string, body: { request: string; max_picks: number }) =>
    request<ShortlistResult>(`/api/modes/color-build/jobs/${jobId}/shortlist`, post(body)),
}

/** Polls a job until it leaves "running", reporting every update. Rejects if the job failed. */
export async function waitForJob(
  id: string,
  onUpdate: (job: Job) => void,
  options: { intervalMs?: number; signal?: AbortSignal; getJob?: (id: string) => Promise<Job> } = {},
): Promise<Job> {
  const { intervalMs = 700, signal, getJob = api.getJob } = options
  for (;;) {
    signal?.throwIfAborted()
    const job = await getJob(id)
    onUpdate(job)
    if (job.status === 'done') return job
    if (job.status === 'failed') throw new Error(job.error ?? 'Пошук завершився помилкою')
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, intervalMs)
      signal?.addEventListener(
        'abort',
        () => {
          clearTimeout(timer)
          reject(signal.reason)
        },
        { once: true },
      )
    })
  }
}
