import { useEffect, useState } from 'react'
import './App.css'

const LANE_LABELS = {
  TOP: '탑',
  JUNGLE: '정글',
  MIDDLE: '미드',
  BOTTOM: '원딜',
  UTILITY: '서포터',
}

function App() {
  const [lanes, setLanes] = useState([])
  const [champions, setChampions] = useState([])
  const [lane, setLane] = useState('TOP')
  const [enemyChampion, setEnemyChampion] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/api/lanes').then((r) => r.json()).then(setLanes).catch(() => {})
    fetch('/api/champions').then((r) => r.json()).then(setChampions).catch(() => {})
  }, [])

  const handleSearch = async (e) => {
    e.preventDefault()
    if (!enemyChampion) return
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
      <h1>롤 밴픽 도우미</h1>
      <p className="subtitle">상대 챔피언을 입력하면 라인별 승률 좋은 카운터 픽을 알려드려요.</p>

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
          placeholder="상대 챔피언 (예: Darius)"
          value={enemyChampion}
          onChange={(e) => setEnemyChampion(e.target.value)}
        />
        <datalist id="champion-list">
          {champions.map((c) => (
            <option key={c} value={c} />
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
                <td>{r.champion}</td>
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

export default App
