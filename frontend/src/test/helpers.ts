import type { Candidate, Job } from '../lib/api'

export function candidate(overrides: Partial<Candidate> = {}): Candidate {
  return {
    skin: 'AWP | Atheris',
    weapon: 'AWP',
    category: 'Rifles',
    offer_id: `offer-${Math.random().toString(36).slice(2)}`,
    title: 'AWP | Atheris (Field-Tested)',
    wear: 'Field-Tested',
    price_cents: 624,
    float_value: 0.2134,
    paint_seed: 12,
    image: 'https://img.example/atheris.png',
    collection: 'The Test Collection',
    rarity: 'Classified',
    coverage: 0.5,
    dominance: 0.9,
    ...overrides,
  }
}

export function doneJob(candidates: Candidate[], overrides: Partial<Job> = {}): Job {
  return {
    id: 'job1',
    status: 'done',
    stage: 'prices',
    done: 10,
    total: 10,
    error: null,
    candidates,
    stats: {
      skins_in_scope: 1753,
      without_color_profile: 0,
      color_matched: 258,
      titles_requested: 730,
      hydrate_failed: 0,
      with_offers_in_budget: candidates.length,
    },
    ...overrides,
  }
}

/** Minimal fetch router: [method, path-prefix] -> JSON body (or a function returning [status, body]). */
export type Handler = unknown | ((init: RequestInit | undefined) => [number, unknown])

export function mockFetch(routes: Record<string, Handler>) {
  const calls: { path: string; init?: RequestInit }[] = []
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    calls.push({ path, init })
    const method = init?.method ?? 'GET'
    const key = Object.keys(routes).find((k) => `${method} ${path}`.startsWith(k))
    if (!key) return new Response(JSON.stringify({ detail: `no mock for ${method} ${path}` }), { status: 404 })
    const handler = routes[key]
    const [status, body] = typeof handler === 'function' ? (handler as (i?: RequestInit) => [number, unknown])(init) : [200, handler]
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fn)
  return { calls, fn }
}
