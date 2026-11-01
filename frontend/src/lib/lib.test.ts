import { afterEach, describe, expect, it, vi } from 'vitest'
import { candidate, mockFetch } from '../test/helpers'
import { ApiError, api, waitForJob, type Job } from './api'
import { dollarsToCents, filterByWeapon, money, orderCategories, sortCandidates, weaponsOf } from './format'

afterEach(() => vi.unstubAllGlobals())

describe('format', () => {
  it('formats cents as dollars', () => {
    expect(money(624)).toBe('$6.24')
    expect(money(5)).toBe('$0.05')
    expect(money(123456)).toBe('$1,234.56')
  })

  it('parses a dollar budget into cents', () => {
    expect(dollarsToCents('50')).toBe(5000)
    expect(dollarsToCents('12,5')).toBe(1250)
    expect(dollarsToCents(' 0.29 ')).toBe(29)
    expect(dollarsToCents('')).toBeNull()
  })

  it.each(['abc', '0', '-5', 'Infinity'])('rejects %j as a budget', (text) => {
    expect(dollarsToCents(text)).toBeNaN()
  })

  const items = [
    candidate({ offer_id: 'a', weapon: 'USP-S', price_cents: 400, coverage: 0.6, float_value: 0.3 }),
    candidate({ offer_id: 'b', weapon: 'AWP', price_cents: 100, coverage: 0.9, float_value: null }),
    candidate({ offer_id: 'c', weapon: 'AWP', price_cents: 900, coverage: 0.9, float_value: 0.05 }),
  ]
  const ids = (list: ReturnType<typeof sortCandidates>) => list.map((c) => c.offer_id)

  it('sorts by colour coverage, then price', () => expect(ids(sortCandidates(items, 'color'))).toEqual(['b', 'c', 'a']))
  it('sorts by price both ways', () => {
    expect(ids(sortCandidates(items, 'price-asc'))).toEqual(['b', 'a', 'c'])
    expect(ids(sortCandidates(items, 'price-desc'))).toEqual(['c', 'a', 'b'])
  })
  it('sorts by float with missing floats last', () => expect(ids(sortCandidates(items, 'float'))).toEqual(['c', 'a', 'b']))
  it('does not mutate its input', () => {
    const before = ids(items)
    sortCandidates(items, 'price-desc')
    expect(ids(items)).toEqual(before)
  })
  it('orders categories sensibly, unknown ones last', () => {
    expect(orderCategories(['Equipment', 'Knives', 'Zebra', 'Rifles', 'Alpha', 'Pistols'])).toEqual([
      'Rifles', 'Pistols', 'Knives', 'Equipment', 'Alpha', 'Zebra',
    ])
  })

  it('filters and lists weapons', () => {
    expect(ids(filterByWeapon(items, 'AWP'))).toEqual(['b', 'c'])
    expect(filterByWeapon(items, '')).toHaveLength(3)
    expect(weaponsOf(items)).toEqual(['AWP', 'USP-S'])
  })
})

describe('request errors', () => {
  it('surfaces the API detail message and status', async () => {
    mockFetch({ 'GET /api/health': () => [503, { detail: 'AI is not configured' }] })
    await expect(api.health()).rejects.toMatchObject({ name: 'Error', status: 503, message: 'AI is not configured' })
    await expect(api.health()).rejects.toBeInstanceOf(ApiError)
  })

  it('formats validation errors (detail as a list) instead of showing [object Object]', async () => {
    mockFetch({ 'GET /api/health': () => [422, { detail: [{ msg: 'bad colour' }] }] })
    await expect(api.health()).rejects.toThrow('bad colour')
  })
})

describe('waitForJob', () => {
  const job = (status: Job['status'], extra: Partial<Job> = {}): Job => ({
    id: 'j', status, stage: '', done: 0, total: 0, error: null, candidates: null, stats: null, ...extra,
  })

  it('polls until done and reports every update', async () => {
    const states = [job('running', { done: 1, total: 3 }), job('running', { done: 2, total: 3 }), job('done')]
    const getJob = vi.fn(async () => states.shift()!)
    const seen: number[] = []
    const result = await waitForJob('j', (j) => seen.push(j.done), { intervalMs: 1, getJob })
    expect(result.status).toBe('done')
    expect(seen).toEqual([1, 2, 0])
    expect(getJob).toHaveBeenCalledTimes(3)
  })

  it('rejects with the server error when the job failed', async () => {
    const getJob = async () => job('failed', { error: 'RuntimeError: dmarket exploded' })
    await expect(waitForJob('j', () => {}, { intervalMs: 1, getJob })).rejects.toThrow('dmarket exploded')
  })

  it('stops when aborted', async () => {
    const controller = new AbortController()
    const getJob = vi.fn(async () => job('running'))
    const pending = waitForJob('j', () => {}, { intervalMs: 50, getJob, signal: controller.signal })
    await new Promise((r) => setTimeout(r, 10))
    controller.abort()
    await expect(pending).rejects.toBeDefined()
    const calls = getJob.mock.calls.length
    await new Promise((r) => setTimeout(r, 80))
    expect(getJob.mock.calls.length).toBe(calls)
  })
})
