import type { Candidate } from './api'

export const COLORS = [
  { id: 'red', label: 'Червоний', swatch: '#e03131' },
  { id: 'orange', label: 'Помаранчевий', swatch: '#f08c00' },
  { id: 'yellow', label: 'Жовтий', swatch: '#fab005' },
  { id: 'green', label: 'Зелений', swatch: '#2f9e44' },
  { id: 'cyan', label: 'Бірюзовий', swatch: '#15aabf' },
  { id: 'blue', label: 'Синій', swatch: '#1c64f2' },
  { id: 'purple', label: 'Фіолетовий', swatch: '#7048e8' },
  { id: 'pink', label: 'Рожевий', swatch: '#d6336c' },
] as const

// ids are the wear names as they appear in market titles, e.g. "AK-47 | Redline (Field-Tested)"
export const WEARS = [
  { id: 'Factory New', label: 'Factory New' },
  { id: 'Minimal Wear', label: 'Minimal Wear' },
  { id: 'Field-Tested', label: 'Field-Tested' },
  { id: 'Well-Worn', label: 'Well-Worn' },
  { id: 'Battle-Scarred', label: 'Battle-Scarred' },
] as const

export const CATEGORY_LABELS: Record<string, string> = {
  Rifles: 'Гвинтівки',
  Pistols: 'Пістолети',
  SMGs: 'Пістолети-кулемети',
  Heavy: 'Важка зброя',
  Knives: 'Ножі',
  Gloves: 'Рукавички',
  Equipment: 'Спорядження',
}

/** Known categories in a sensible order (weapons first), unknown ones after, alphabetically. */
export function orderCategories(categories: string[]): string[] {
  const known = Object.keys(CATEGORY_LABELS)
  const rank = (c: string) => (known.includes(c) ? known.indexOf(c) : known.length)
  return [...categories].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
}

export function money(cents: number): string {
  return `$${(cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/** "50" / "12.5" / "" -> cents (or null for empty). NaN and negatives are rejected as null-with-error by the caller. */
export function dollarsToCents(text: string): number | null {
  const trimmed = text.trim().replace(',', '.')
  if (trimmed === '') return null
  const value = Number(trimmed)
  if (!Number.isFinite(value) || value <= 0) return NaN
  return Math.round(value * 100)
}

export type SortKey = 'color' | 'price-asc' | 'price-desc' | 'float'

export const SORT_LABELS: Record<SortKey, string> = {
  color: 'За покриттям кольором',
  'price-asc': 'Ціна: від дешевих',
  'price-desc': 'Ціна: від дорогих',
  float: 'Float: від меншого',
}

export function sortCandidates(items: Candidate[], key: SortKey): Candidate[] {
  const copy = [...items]
  switch (key) {
    case 'color':
      return copy.sort((a, b) => b.coverage - a.coverage || a.price_cents - b.price_cents)
    case 'price-asc':
      return copy.sort((a, b) => a.price_cents - b.price_cents)
    case 'price-desc':
      return copy.sort((a, b) => b.price_cents - a.price_cents)
    case 'float':
      return copy.sort((a, b) => (a.float_value ?? Infinity) - (b.float_value ?? Infinity))
  }
}

export function filterByWeapon(items: Candidate[], weapon: string): Candidate[] {
  return weapon ? items.filter((c) => c.weapon === weapon) : items
}

export function weaponsOf(items: Candidate[]): string[] {
  return [...new Set(items.map((c) => c.weapon))].sort((a, b) => a.localeCompare(b))
}

export const STAGE_LABELS: Record<string, string> = {
  colors: 'Аналіз кольору скінів',
  prices: 'Завантаження цін з DMarket',
}
