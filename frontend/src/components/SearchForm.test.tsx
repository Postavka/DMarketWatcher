import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SearchForm } from './SearchForm'

function setup(props: Partial<React.ComponentProps<typeof SearchForm>> = {}) {
  const onSubmit = vi.fn()
  const onSideChange = vi.fn()
  render(<SearchForm categories={['Rifles', 'Pistols']} busy={false} onSideChange={onSideChange} onSubmit={onSubmit} {...props} />)
  return { onSubmit, onSideChange, user: userEvent.setup() }
}

const submitButton = () => screen.getByRole('button', { name: /підібрати|шукаю/i })

describe('SearchForm', () => {
  it('cannot be submitted until a colour is chosen', async () => {
    const { user } = setup()
    expect(submitButton()).toBeDisabled()
    expect(screen.getByText('Виберіть хоча б один колір.')).toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: 'Синій' }))
    expect(submitButton()).toBeEnabled()
  })

  it('submits the default search with the chosen colour', async () => {
    const { user, onSubmit } = setup()
    await user.click(screen.getByRole('checkbox', { name: 'Синій' }))
    await user.click(submitButton())
    expect(onSubmit).toHaveBeenCalledWith({
      side: 'ct',
      colors: ['blue'],
      budget_cents: 5000,
      categories: [],
      weapons: [],
      wears: ['Factory New', 'Minimal Wear', 'Field-Tested'],
      stattrak: false,
      per_weapon: 3,
      limit: 100,
    })
  })

  it('sends several colours, a custom budget, categories, side and StatTrak', async () => {
    const { user, onSubmit, onSideChange } = setup()
    await user.click(screen.getByRole('checkbox', { name: 'Синій' }))
    await user.click(screen.getByRole('checkbox', { name: 'Бірюзовий' }))
    await user.click(screen.getByRole('radio', { name: /Терористи \(T\)/ }))
    expect(onSideChange).toHaveBeenCalledWith('t')
    await user.click(screen.getByRole('checkbox', { name: 'Пістолети' }))
    await user.click(screen.getByRole('checkbox', { name: /StatTrak/ }))
    await user.clear(screen.getByLabelText(/Бюджет/))
    await user.type(screen.getByLabelText(/Бюджет/), '12,5')
    await user.click(submitButton())
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        side: 't',
        colors: ['blue', 'cyan'],
        budget_cents: 1250,
        categories: ['Pistols'],
        stattrak: true,
      }),
    )
  })

  it('treats empty budget and per-weapon limits as "no limit"', async () => {
    const { user, onSubmit } = setup()
    await user.click(screen.getByRole('checkbox', { name: 'Червоний' }))
    await user.clear(screen.getByLabelText(/Бюджет/))
    await user.clear(screen.getByLabelText(/Скінів на зброю/))
    await user.click(submitButton())
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ budget_cents: null, per_weapon: null }))
  })

  it('sends no wear filter when every wear is selected', async () => {
    const { user, onSubmit } = setup()
    await user.click(screen.getByRole('checkbox', { name: 'Синій' }))
    await user.click(screen.getByRole('checkbox', { name: 'Well-Worn' }))
    await user.click(screen.getByRole('checkbox', { name: 'Battle-Scarred' }))
    await user.click(submitButton())
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ wears: [] }))
  })

  it.each([
    ['budget', /Бюджет/, 'abc', /Бюджет має бути числом/],
    ['budget', /Бюджет/, '-3', /Бюджет має бути числом/],
    ['per-weapon', /Скінів на зброю/, '0', /ціле число від 1/],
    ['per-weapon', /Скінів на зброю/, '2.5', /ціле число від 1/],
  ])('rejects an invalid %s value (%s)', async (_name, label, text, message) => {
    const { user, onSubmit } = setup()
    await user.click(screen.getByRole('checkbox', { name: 'Синій' }))
    await user.clear(screen.getByLabelText(label))
    await user.type(screen.getByLabelText(label), text)
    await user.click(submitButton())
    expect(screen.getByRole('alert')).toHaveTextContent(message)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('clears chosen categories when the side changes', async () => {
    const { user, onSubmit } = setup()
    await user.click(screen.getByRole('checkbox', { name: 'Синій' }))
    await user.click(screen.getByRole('checkbox', { name: 'Гвинтівки' }))
    await user.click(screen.getByRole('radio', { name: /Терористи \(T\)/ }))
    await user.click(submitButton())
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ side: 't', categories: [] }))
  })

  it('is disabled while a search is running', () => {
    setup({ busy: true })
    expect(submitButton()).toBeDisabled()
    expect(submitButton()).toHaveTextContent('Шукаю')
  })
})
