import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { candidate, mockFetch } from '../test/helpers'
import { ShortlistPanel } from './ShortlistPanel'

afterEach(() => vi.unstubAllGlobals())

describe('ShortlistPanel', () => {
  it('is disabled and explains how to enable AI when there is no key', () => {
    render(<ShortlistPanel jobId="j1" aiEnabled={false} />)
    expect(screen.getByRole('note')).toHaveTextContent('ANTHROPIC_API_KEY')
    expect(screen.getByRole('textbox')).toBeDisabled()
    expect(screen.getByRole('button', { name: /Вибрати найкращі/ })).toBeDisabled()
  })

  it('needs a request text before it can be sent', async () => {
    render(<ShortlistPanel jobId="j1" aiEnabled />)
    const button = screen.getByRole('button', { name: /Вибрати найкращі/ })
    expect(button).toBeDisabled()
    await userEvent.setup().type(screen.getByRole('textbox'), 'чистий синій')
    expect(button).toBeEnabled()
  })

  it('sends the request to the job endpoint and shows picks with reasons', async () => {
    const pick = candidate({ skin: 'USP-S | Blueprint', offer_id: 'p1' })
    const { calls } = mockFetch({
      'POST /api/modes/color-build/jobs/j1/shortlist': { picks: [{ candidate: pick, reason: 'Чистий синій колір' }], ignored: [], input_tokens: 1, output_tokens: 1 },
    })
    const user = userEvent.setup()
    render(<ShortlistPanel jobId="j1" aiEnabled />)
    await user.type(screen.getByRole('textbox'), '  без мультяшних  ')
    await user.selectOptions(screen.getByLabelText(/Скільки показати/), '5')
    await user.click(screen.getByRole('button', { name: /Вибрати найкращі/ }))

    expect(await screen.findByText('Чистий синій колір')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /USP-S \| Blueprint/ })).toBeInTheDocument()
    expect(JSON.parse(calls[0].init!.body as string)).toEqual({ request: 'без мультяшних', max_picks: 5 })
  })

  it('shows the server message when the AI step fails', async () => {
    mockFetch({ 'POST /api/modes/color-build/jobs/j1/shortlist': () => [422, { detail: 'the model declined this request (cyber)' }] })
    const user = userEvent.setup()
    render(<ShortlistPanel jobId="j1" aiEnabled />)
    await user.type(screen.getByRole('textbox'), 'щось')
    await user.click(screen.getByRole('button', { name: /Вибрати найкращі/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('declined this request')
  })

  it('says so when the model keeps nothing', async () => {
    mockFetch({ 'POST /api/modes/color-build/jobs/j1/shortlist': { picks: [], ignored: [], input_tokens: 1, output_tokens: 1 } })
    const user = userEvent.setup()
    render(<ShortlistPanel jobId="j1" aiEnabled />)
    await user.type(screen.getByRole('textbox'), 'щось')
    await user.click(screen.getByRole('button', { name: /Вибрати найкращі/ }))
    expect(await screen.findByText(/Жоден із кандидатів/)).toBeInTheDocument()
  })
})
