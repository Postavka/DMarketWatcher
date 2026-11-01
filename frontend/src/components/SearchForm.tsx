import { useState, type FormEvent } from 'react'
import type { SearchParams, Side } from '../lib/api'
import { CATEGORY_LABELS, COLORS, WEARS, dollarsToCents } from '../lib/format'

interface Props {
  categories: string[]
  busy: boolean
  onSideChange: (side: Side) => void
  onSubmit: (params: SearchParams) => void
}

const DEFAULT_WEARS = ['Factory New', 'Minimal Wear', 'Field-Tested']

function toggled(set: Set<string>, value: string): Set<string> {
  const next = new Set(set)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  return next
}

export function SearchForm({ categories, busy, onSideChange, onSubmit }: Props) {
  const [side, setSide] = useState<Side>('ct')
  const [colors, setColors] = useState(new Set<string>())
  const [wears, setWears] = useState(new Set(DEFAULT_WEARS))
  const [chosenCategories, setChosenCategories] = useState(new Set<string>())
  const [budget, setBudget] = useState('50')
  const [perWeapon, setPerWeapon] = useState('3')
  const [limit, setLimit] = useState(100)
  const [stattrak, setStattrak] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function changeSide(next: Side) {
    setSide(next)
    setChosenCategories(new Set())
    onSideChange(next)
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    const budgetCents = dollarsToCents(budget)
    if (Number.isNaN(budgetCents)) return setError('Бюджет має бути числом більше нуля (або залиште поле порожнім).')
    const perWeaponValue = perWeapon.trim() === '' ? null : Number(perWeapon)
    if (perWeaponValue !== null && (!Number.isInteger(perWeaponValue) || perWeaponValue < 1))
      return setError('«Скінів на зброю» — ціле число від 1 (або залиште порожнім).')
    setError(null)
    onSubmit({
      side,
      colors: [...colors],
      budget_cents: budgetCents,
      categories: [...chosenCategories],
      weapons: [],
      wears: wears.size === WEARS.length ? [] : [...wears],
      stattrak,
      per_weapon: perWeaponValue,
      limit,
    })
  }

  return (
    <form className="panel form" onSubmit={submit}>
      <fieldset>
        <legend>Сторона</legend>
        <div className="segmented" role="radiogroup" aria-label="Сторона">
          {(['ct', 't'] as const).map((value) => (
            <label key={value} className={side === value ? 'on' : ''}>
              <input type="radio" name="side" checked={side === value} onChange={() => changeSide(value)} />
              {value === 'ct' ? 'Контр-терористи (CT)' : 'Терористи (T)'}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend>Колір</legend>
        <div className="chips">
          {COLORS.map((c) => (
            <label key={c.id} className={`chip ${colors.has(c.id) ? 'on' : ''}`}>
              <input type="checkbox" checked={colors.has(c.id)} onChange={() => setColors(toggled(colors, c.id))} />
              <span className="swatch" style={{ background: c.swatch }} aria-hidden="true" />
              {c.label}
            </label>
          ))}
        </div>
        <p className="hint">Можна вибрати кілька суміжних відтінків, наприклад синій і бірюзовий.</p>
      </fieldset>

      <div className="row">
        <label className="field">
          Бюджет на предмет, $
          <input inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="без обмеження" />
        </label>
        <label className="field">
          Скінів на зброю
          <input inputMode="numeric" value={perWeapon} onChange={(e) => setPerWeapon(e.target.value)} placeholder="без обмеження" />
        </label>
        <label className="field">
          Усього кандидатів
          <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
            {[30, 50, 100, 200].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>

      <fieldset>
        <legend>Знос</legend>
        <div className="chips">
          {WEARS.map((w) => (
            <label key={w.id} className={`chip ${wears.has(w.id) ? 'on' : ''}`}>
              <input type="checkbox" checked={wears.has(w.id)} onChange={() => setWears(toggled(wears, w.id))} />
              {w.label}
            </label>
          ))}
        </div>
      </fieldset>

      {categories.length > 0 && (
        <fieldset>
          <legend>Категорії (усі, якщо нічого не вибрано)</legend>
          <div className="chips">
            {categories.map((c) => (
              <label key={c} className={`chip ${chosenCategories.has(c) ? 'on' : ''}`}>
                <input
                  type="checkbox"
                  checked={chosenCategories.has(c)}
                  onChange={() => setChosenCategories(toggled(chosenCategories, c))}
                />
                {CATEGORY_LABELS[c] ?? c}
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <label className="check">
        <input type="checkbox" checked={stattrak} onChange={(e) => setStattrak(e.target.checked)} />
        Лише StatTrak™
      </label>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" className="primary" disabled={busy || colors.size === 0}>
          {busy ? 'Шукаю…' : 'Підібрати скіни'}
        </button>
        {colors.size === 0 && <span className="hint">Виберіть хоча б один колір.</span>}
      </div>
    </form>
  )
}
