import { useMemo, useState } from 'react'
import type { Candidate, SelectionStats } from '../lib/api'
import { SORT_LABELS, filterByWeapon, sortCandidates, weaponsOf, type SortKey } from '../lib/format'
import { CandidateCard } from './CandidateCard'

interface Props {
  candidates: Candidate[]
  stats: SelectionStats | null
}

export function Results({ candidates, stats }: Props) {
  const [sort, setSort] = useState<SortKey>('color')
  const [weapon, setWeapon] = useState('')
  const weapons = useMemo(() => weaponsOf(candidates), [candidates])
  const shown = useMemo(() => sortCandidates(filterByWeapon(candidates, weapon), sort), [candidates, weapon, sort])

  return (
    <section className="panel" aria-label="Результати">
      <header className="results-head">
        <h2>
          Знайдено: {shown.length}
          {weapon && ` з ${candidates.length}`}
        </h2>
        <div className="row">
          <label className="field inline">
            Сортування
            <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
              {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
                <option key={key} value={key}>
                  {SORT_LABELS[key]}
                </option>
              ))}
            </select>
          </label>
          <label className="field inline">
            Зброя
            <select value={weapon} onChange={(e) => setWeapon(e.target.value)}>
              <option value="">Уся</option>
              {weapons.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      {stats && (
        <p className="muted small" data-testid="stats">
          Скінів у вибраній області: {stats.skins_in_scope} → підходять за кольором: {stats.color_matched} → мають
          лот у бюджеті: {stats.with_offers_in_budget}
          {stats.without_color_profile > 0 && ` · без картинки для аналізу: ${stats.without_color_profile}`}
          {stats.hydrate_failed > 0 && ` · не вдалось завантажити ціни для ${stats.hydrate_failed} назв (спробуйте ще раз)`}
        </p>
      )}

      {shown.length === 0 ? (
        <p className="empty">
          Нічого не знайдено. Спробуйте збільшити бюджет, додати знос або вибрати суміжний відтінок кольору.
        </p>
      ) : (
        <ul className="grid">
          {shown.map((c) => (
            <CandidateCard key={c.offer_id} candidate={c} />
          ))}
        </ul>
      )}
    </section>
  )
}
