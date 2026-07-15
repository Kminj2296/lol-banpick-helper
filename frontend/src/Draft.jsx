import { useEffect, useMemo, useState } from 'react'
import { ALL_LANES, LANE_LABELS } from './laneLabels'

// 정식 프로 대회 밴픽 순서: 밴6(B-R-B-R-B-R) → 픽6(B-R-R-B-B-R) → 밴4(R-B-R-B) → 픽4(R-B-B-R)
const DRAFT_SEQUENCE = [
  { type: 'ban', team: 'blue' }, { type: 'ban', team: 'red' },
  { type: 'ban', team: 'blue' }, { type: 'ban', team: 'red' },
  { type: 'ban', team: 'blue' }, { type: 'ban', team: 'red' },
  { type: 'pick', team: 'blue' }, { type: 'pick', team: 'red' },
  { type: 'pick', team: 'red' }, { type: 'pick', team: 'blue' },
  { type: 'pick', team: 'blue' }, { type: 'pick', team: 'red' },
  { type: 'ban', team: 'red' }, { type: 'ban', team: 'blue' },
  { type: 'ban', team: 'red' }, { type: 'ban', team: 'blue' },
  { type: 'pick', team: 'red' }, { type: 'pick', team: 'blue' },
  { type: 'pick', team: 'blue' }, { type: 'pick', team: 'red' },
]

const TEAM_LABELS = { blue: '블루팀', red: '레드팀' }

function TeamPanel({ label, picks, className }) {
  return (
    <div className={`team-panel ${className}`}>
      <h3>{label}</h3>
      <ul className="pick-list">
        {ALL_LANES.map((lane) => {
          const pick = picks.find((p) => p.lane === lane)
          return (
            <li key={lane}>
              <span className="lane-tag">{LANE_LABELS[lane]}</span>
              <span className="pick-champ">{pick ? pick.champion : '-'}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function Draft() {
  const [champions, setChampions] = useState([])
  const [topChampions, setTopChampions] = useState([])
  const [stepIndex, setStepIndex] = useState(0)
  const [banned, setBanned] = useState([])
  const [blue, setBlue] = useState([])
  const [red, setRed] = useState([])
  const [selectedLane, setSelectedLane] = useState('TOP')
  const [inputValue, setInputValue] = useState('')
  const [recommendations, setRecommendations] = useState([])
  const [loadingRec, setLoadingRec] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/api/champions').then((r) => r.json()).then(setChampions).catch(() => {})
    fetch('/api/top-champions?min_games=5').then((r) => r.json()).then(setTopChampions).catch(() => {})
  }, [])

  const currentStep = stepIndex < DRAFT_SEQUENCE.length ? DRAFT_SEQUENCE[stepIndex] : null
  const currentTeamPicks = currentStep?.team === 'blue' ? blue : red
  const enemyTeamPicks = currentStep?.team === 'blue' ? red : blue

  const availableLanes = useMemo(() => {
    const taken = currentTeamPicks.map((p) => p.lane)
    return ALL_LANES.filter((l) => !taken.includes(l))
  }, [currentTeamPicks])

  const excludedChampions = useMemo(
    () => [...banned, ...blue.map((p) => p.champion), ...red.map((p) => p.champion)],
    [banned, blue, red],
  )

  useEffect(() => {
    if (currentStep?.type === 'pick' && !availableLanes.includes(selectedLane)) {
      setSelectedLane(availableLanes[0] || 'TOP')
    }
  }, [currentStep, availableLanes, selectedLane])

  useEffect(() => {
    if (currentStep?.type !== 'pick' || !selectedLane) {
      setRecommendations([])
      return
    }
    setLoadingRec(true)
    setError('')
    fetch('/api/draft/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lane: selectedLane,
        allies: currentTeamPicks.map((p) => p.champion),
        enemies: enemyTeamPicks.map((p) => p.champion),
        banned: excludedChampions,
        min_games: 3,
      }),
    })
      .then((r) => {
        if (!r.ok) throw new Error()
        return r.json()
      })
      .then(setRecommendations)
      .catch(() => {
        setError('추천을 불러오지 못했습니다. 백엔드 서버 상태를 확인하세요.')
        setRecommendations([])
      })
      .finally(() => setLoadingRec(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStep, selectedLane, excludedChampions])

  const confirmPick = (champion) => {
    if (!champion || !currentStep) return
    const entry = { champion, lane: selectedLane }
    if (currentStep.team === 'blue') setBlue((prev) => [...prev, entry])
    else setRed((prev) => [...prev, entry])
    setStepIndex((i) => i + 1)
    setInputValue('')
  }

  const confirmBan = (champion) => {
    if (!champion || !currentStep) return
    setBanned((prev) => [...prev, champion])
    setStepIndex((i) => i + 1)
    setInputValue('')
  }

  const handleReset = () => {
    setStepIndex(0)
    setBanned([])
    setBlue([])
    setRed([])
    setInputValue('')
    setRecommendations([])
  }

  const banSuggestions = topChampions.filter((c) => !excludedChampions.includes(c.champion)).slice(0, 8)

  return (
    <div className="container draft-container">
      <p className="subtitle">
        정식 대회 밴픽 순서(밴6-픽6-밴4-픽4)를 따라가면서, 픽 차례마다 라인을 고르면 지금까지의 아군/적군 조합을
        고려한 추정 승률로 추천 챔피언을 보여줘요.
      </p>

      <div className="draft-status">
        {currentStep ? (
          <p>
            <strong>{stepIndex + 1}/20단계</strong> — {TEAM_LABELS[currentStep.team]}{' '}
            {currentStep.type === 'ban' ? '밴' : '픽'}
          </p>
        ) : (
          <p><strong>드래프트 완료</strong></p>
        )}
        <button type="button" onClick={handleReset} className="reset-button">처음부터</button>
      </div>

      <div className="draft-board">
        <TeamPanel label={`블루팀${currentStep?.team === 'blue' ? ' (진행중)' : ''}`} picks={blue} className="blue" />
        <TeamPanel label={`레드팀${currentStep?.team === 'red' ? ' (진행중)' : ''}`} picks={red} className="red" />
      </div>

      <div className="ban-list">
        <strong>밴:</strong> {banned.length ? banned.join(', ') : '없음'}
      </div>

      {currentStep?.type === 'pick' && (
        <div className="pick-controls">
          <select value={selectedLane} onChange={(e) => setSelectedLane(e.target.value)}>
            {availableLanes.map((l) => (
              <option key={l} value={l}>{LANE_LABELS[l]}</option>
            ))}
          </select>
          <input
            list="all-champion-list"
            placeholder="직접 입력해서 픽"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
          />
          <button type="button" onClick={() => confirmPick(inputValue)} disabled={!inputValue}>
            이 챔피언으로 확정
          </button>
        </div>
      )}

      {currentStep?.type === 'ban' && (
        <div className="pick-controls">
          <input
            list="all-champion-list"
            placeholder="밴할 챔피언 입력"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
          />
          <button type="button" onClick={() => confirmBan(inputValue)} disabled={!inputValue}>
            밴 확정
          </button>
          {banSuggestions.length > 0 && (
            <div className="ban-suggestions">
              <span>전체 승률 상위 챔피언:</span>
              {banSuggestions.map((c) => (
                <button key={c.champion} type="button" className="chip-button" onClick={() => confirmBan(c.champion)}>
                  {c.champion} ({c.win_rate}%)
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <datalist id="all-champion-list">
        {champions.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>

      {error && <p className="error">{error}</p>}

      {currentStep?.type === 'pick' && (
        <>
          {loadingRec && <p className="hint">추천 계산 중...</p>}
          {!loadingRec && recommendations.length === 0 && (
            <p className="hint">표본이 부족하거나 조건에 맞는 추천이 없어요.</p>
          )}
          {!loadingRec && recommendations.length > 0 && (
            <table className="result-table">
              <thead>
                <tr>
                  <th>순위</th>
                  <th>챔피언</th>
                  <th>기본 승률</th>
                  <th>추정 승률</th>
                  <th>표본</th>
                  <th>근거</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {recommendations.map((r, i) => (
                  <tr key={r.champion}>
                    <td>{i + 1}</td>
                    <td>{r.champion}</td>
                    <td>{r.base_win_rate}%</td>
                    <td><strong>{r.estimated_win_rate}%</strong></td>
                    <td>{r.base_games}</td>
                    <td className="components-cell">
                      {r.components.slice(0, 3).map((c, idx) => (
                        <div key={idx} className={`component ${c.delta >= 0 ? 'positive' : 'negative'}`}>
                          {c.type === 'synergy' ? `+${c.with}` : `vs ${c.vs}`}: {c.delta > 0 ? '+' : ''}{c.delta}%p
                        </div>
                      ))}
                    </td>
                    <td>
                      <button type="button" onClick={() => confirmPick(r.champion)}>선택</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}

export default Draft
