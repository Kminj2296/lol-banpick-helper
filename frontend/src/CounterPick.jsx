import { useEffect, useState } from 'react'
import { LANE_LABELS } from './laneLabels'
import { useChampionNames } from './useChampionNames'

function CounterPick() {
  const [lanes, setLanes] = useState([])
  const [lane, setLane] = useState('TOP')
  const [enemyInput, setEnemyInput] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const { displayName, resolve, searchOptions } = useChampionNames()

  useEffect(() => {
    fetch('/api/lanes').then((r) => r.json()).then(setLanes).catch(() => {})
  }, [])

  const handleSearch = async (e) => {
    e.preventDefault()
    const enemyChampion = resolve(enemyInput)
    if (!enemyChampion) {
      setError('챔피언 이름을 목록에서 정확히 선택해주세요 (한글/영문 둘 다 가능).')
      return
    }
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ lane, enemy_champion: enemyChampion })
      const res = await fetch(`/api/recommend?${params}`)
      if (!res.ok) throw new Error(await res.text())
      setResults(await res.json())
    } catch (err) {
      setError('추천을 불러오지 못했습니다. 백엔드 서버와 데이터 수집 상태를 확인하세요.')
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <p className="subtitle">상대 챔피언을 입력하면 라인별 승률 좋은 카운터 픽을 알려드려요. (같은 라인 1대1 기준)</p>

      <form onSubmit={handleSearch} className="search-form">
        <select value={lane} onChange={(e) => setLane(e.target.value)}>
          {(lanes.length ? lanes : Object.keys(LANE_LABELS)).map((l) => (
            <option key={l} value={l}>
              {LANE_LABELS[l] || l}
            </option>
          ))}
        </select>

        <input
          list="champion-list"
          placeholder="상대 챔피언 (한글 또는 영문, 예: 다리우스)"
          value={enemyInput}
          onChange={(e) => setEnemyInput(e.target.value)}
        />
        <datalist id="champion-list">
          {searchOptions.map((c) => (
            <option key={c.en} value={c.label} />
          ))}
        </datalist>

        <button type="submit" disabled={loading}>
          {loading ? '검색 중...' : '추천 받기'}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {results.length > 0 && (
        <table className="result-table">
          <thead>
            <tr>
              <th>순위</th>
              <th>챔피언</th>
              <th>승률</th>
              <th>표본(게임 수)</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r, i) => (
              <tr key={r.champion}>
                <td>{i + 1}</td>
                <td>{displayName(r.champion)}</td>
                <td>{r.win_rate}%</td>
                <td>{r.games}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!loading && !error && results.length === 0 && (
        <p className="hint">라인과 상대 챔피언을 선택하고 검색해보세요.</p>
      )}
    </div>
  )
}

export default CounterPick
