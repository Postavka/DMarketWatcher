import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { candidate, doneJob, mockFetch } from './test/helpers'

afterEach(() => vi.unstubAllGlobals())

const slots = [
  { category: 'Rifles', weapon: 'AWP', skins: 10 },
  { category: 'Pistols', weapon: 'USP-S', skins: 5 },
]
const health = { status: 'ok', catalog_skins: 2126, ai_enabled: false }

async function runSearch(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('checkbox', { name: 'Синій' }))
  await user.click(screen.getByRole('button', { name: /Підібрати скіни/ }))
}

describe('App', () => {
  it('runs a search end to end and shows the results with the pipeline stats', async () => {
    const found = [
      candidate({ skin: 'AWP | Atheris', weapon: 'AWP', offer_id: 'a', price_cents: 624 }),
      candidate({ skin: 'USP-S | Blueprint', weapon: 'USP-S', offer_id: 'b', price_cents: 417, coverage: 0.9 }),
    ]
    const { calls } = mockFetch({
      'GET /api/health': health,
      'GET /api/catalog/slots': slots,
      'POST /api/modes/color-build/search': () => [202, { job_id: 'job1' }],
      'GET /api/jobs/job1': doneJob(found),
    })
    const user = userEvent.setup()
    render(<App />)
    await runSearch(user)

    const results = await screen.findByRole('region', { name: 'Результати' })
    expect(within(results).getByRole('heading', { name: 'Знайдено: 2' })).toBeInTheDocument()
    expect(within(results).getByText('$6.24')).toBeInTheDocument()
    expect(within(results).getByTestId('stats')).toHaveTextContent('1753 → підходять за кольором: 258 → мають лот у бюджеті: 2')
    const titles = within(results).getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
    expect(titles).toEqual(['USP-S | Blueprint', 'AWP | Atheris']) // default sort: colour coverage

    const sent = JSON.parse(calls.find((c) => c.path === '/api/modes/color-build/search')!.init!.body as string)
    expect(sent).toMatchObject({ side: 'ct', colors: ['blue'], budget_cents: 5000 })
  })

  it('filters results by weapon and re-sorts them', async () => {
    mockFetch({
      'GET /api/health': health,
      'GET /api/catalog/slots': slots,
      'POST /api/modes/color-build/search': () => [202, { job_id: 'job1' }],
      'GET /api/jobs/job1': doneJob([
        candidate({ skin: 'AWP | Atheris', weapon: 'AWP', offer_id: 'a', price_cents: 624, coverage: 0.5 }),
        candidate({ skin: 'USP-S | Blueprint', weapon: 'USP-S', offer_id: 'b', price_cents: 417, coverage: 0.9 }),
        candidate({ skin: 'AWP | Hydra', weapon: 'AWP', offer_id: 'c', price_cents: 100, coverage: 0.7 }),
      ]),
    })
    const user = userEvent.setup()
    render(<App />)
    await runSearch(user)
    const results = await screen.findByRole('region', { name: 'Результати' })
    const names = () => within(results).getAllByRole('heading', { level: 3 }).map((h) => h.textContent)

    await user.selectOptions(within(results).getByLabelText('Сортування'), 'price-asc')
    expect(names()).toEqual(['AWP | Hydra', 'USP-S | Blueprint', 'AWP | Atheris'])
    await user.selectOptions(within(results).getByLabelText('Зброя'), 'AWP')
    expect(names()).toEqual(['AWP | Hydra', 'AWP | Atheris'])
    expect(within(results).getByRole('heading', { name: 'Знайдено: 2 з 3' })).toBeInTheDocument()
  })

  it('shows progress while the job is running', async () => {
    const running = { ...doneJob([]), status: 'running', stage: 'prices', done: 3, total: 10, candidates: null, stats: null }
    mockFetch({
      'GET /api/health': health,
      'GET /api/catalog/slots': slots,
      'POST /api/modes/color-build/search': () => [202, { job_id: 'job1' }],
      'GET /api/jobs/job1': running,
    })
    const user = userEvent.setup()
    render(<App />)
    await runSearch(user)
    expect(await screen.findByRole('status')).toHaveTextContent('Завантаження цін з DMarket — 3 з 10')
    expect(screen.getByRole('button', { name: /Шукаю/ })).toBeDisabled()
  })

  it('explains an empty result', async () => {
    mockFetch({
      'GET /api/health': health,
      'GET /api/catalog/slots': slots,
      'POST /api/modes/color-build/search': () => [202, { job_id: 'job1' }],
      'GET /api/jobs/job1': doneJob([]),
    })
    const user = userEvent.setup()
    render(<App />)
    await runSearch(user)
    expect(await screen.findByText(/Нічого не знайдено/)).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'AI-добір' })).not.toBeInTheDocument()
  })

  it('shows the AI panel after results, disabled when the server has no key', async () => {
    mockFetch({
      'GET /api/health': health,
      'GET /api/catalog/slots': slots,
      'POST /api/modes/color-build/search': () => [202, { job_id: 'job1' }],
      'GET /api/jobs/job1': doneJob([candidate()]),
    })
    const user = userEvent.setup()
    render(<App />)
    await runSearch(user)
    const panel = await screen.findByRole('region', { name: 'AI-добір' })
    expect(within(panel).getByRole('note')).toHaveTextContent('ANTHROPIC_API_KEY')
  })

  it('reports a failed job', async () => {
    mockFetch({
      'GET /api/health': health,
      'GET /api/catalog/slots': slots,
      'POST /api/modes/color-build/search': () => [202, { job_id: 'job1' }],
      'GET /api/jobs/job1': { ...doneJob([]), status: 'failed', error: 'HTTPStatusError: 429', candidates: null, stats: null },
    })
    const user = userEvent.setup()
    render(<App />)
    await runSearch(user)
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTPStatusError: 429')
    expect(screen.getByRole('button', { name: /Підібрати скіни/ })).toBeEnabled()
  })

  it('shows the server message when the search cannot start', async () => {
    mockFetch({
      'GET /api/health': { ...health, catalog_skins: 0 },
      'GET /api/catalog/slots': slots,
      'POST /api/modes/color-build/search': () => [503, { detail: 'skin catalog is not loaded yet' }],
    })
    const user = userEvent.setup()
    render(<App />)
    expect(await screen.findByText(/Каталог скінів ще порожній/)).toBeInTheDocument()
    await runSearch(user)
    expect(await screen.findByRole('alert')).toHaveTextContent('skin catalog is not loaded yet')
  })

  it('tells the user when the backend is down', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Сервер недоступний')
  })

  it('loads categories for the chosen side', async () => {
    const { calls } = mockFetch({ 'GET /api/health': health, 'GET /api/catalog/slots': slots })
    const user = userEvent.setup()
    render(<App />)
    expect(await screen.findByRole('checkbox', { name: 'Гвинтівки' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Пістолети' })).toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: /Терористи \(T\)/ }))
    expect(calls.some((c) => c.path === '/api/catalog/slots?side=t')).toBe(true)
  })
})
