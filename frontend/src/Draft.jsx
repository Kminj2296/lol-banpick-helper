import { useEffect, useMemo, useState } from 'react'
import { ALL_LANES, LANE_LABELS } from './laneLabels'
import { useChampionNames } from './useChampionNames'

// 솔로랭크 밴픽 순서: 밴10(B-R 번갈아 5개씩) → 픽10(1-2-2-2-2-1, B부터 스네이크)
const SOLOQ_SEQUENCE = [
  { type: 'ban', team: 'blue' }, { type: 'ban', team: 'red' },
  { type: 'ban', team: 'blue' }, { type: 'ban', team: 'red' },
  { type: 'ban', team: 'blue' }, { type: 'ban', team: 'red' },
  { type: 'ban', team: 'blue' }, { type: 'ban', team: 'red' },
  { type: 'ban', team: 'blue' }, { type: 'ban', team: 'red' },
  { type: 'pick', team: 'blue' },
  { type: 'pick', team: 'red' }, { type: 'pick', team: 'red' },
  { type: 'pick', team: 'blue' }, { type: 'pick', team: 'blue' },
  { type: 'pick', team: 'red' }, { type: 'pick', team: 'red' },
  { type: 'pick', team: 'blue' }, { type: 'pick', team: 'blue' },
  { type: 'pick', team: 'red' },
]

// 대회(프로) 밴픽 순서: 밴6(B-R-B-R-B-R) → 픽6(B-R-R-B-B-R) → 밴4(R-B-R-B) → 픽4(R-B-B-R)
const TOURNAMENT_SEQUENCE = [
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

const MODES = {
  soloq: { label: '솔로랭크 순서 (밴10 → 픽1-2-2-2-2-1)', sequence: SOLOQ_SEQUENCE },
  tournament: { label: '대회 순서 (밴6→픽6→밴4→픽4)', sequence: TOURNAMENT_SEQUENCE },
}

const TEAM_LABELS = { blue: '블루팀', red: '레드팀' }

function TeamPanel({ label, picks, className, displayName }) {
  return (
    <div className={`team-panel ${className}`}>
      <h3>{label}</h3>
      <ul className="pick-list">
        {ALL_LANES.map((lane) => {
          const pick = picks.find((p) => p.lane === lane)
          return (
            <li key={lane}>
              <span className="lane-tag">{LANE_LABELS[lane]}</span>
              <span className="pick-champ">{pick ? displayName(pick.champion) : '-'}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function Draft() {
  const [mode, setMode] = useState('soloq')
  const [topChampions, setTopChampions] = useState([])
  const [banLane, setBanLane] = useState('TOP')
  const [stepIndex, setStepIndex] = useState(0)
  const [banned, setBanned] = useState([]) // { champion, team }
  const [blue, setBlue] = useState([])
  const [red, setRed] = useState([])
  const [selectedLane, setSelectedLane] = useState('TOP')
  const [inputValue, setInputValue] = useState('')
  const [recommendations, setRecommendations] = useState([])
  const [loadingRec, setLoadingRec] = useState(false)
  const [error, setError] = useState('')
  const { displayName, resolve, searchOptions } = useChampionNames()

  const draftSequence = MODES[mode].sequence

  useEffect(() => {
    fetch(`/api/top-champions?min_games=5&lane=${banLane}`).then((r) => r.json()).then(setTopChampions).catch(() => {})
  }, [banLane])

  const currentStep = stepIndex < draftSequence.length ? draftSequence[stepIndex] : null
  const currentTeamPicks = currentStep?.team === 'blue' ? blue : red
  const enemyTeamPicks = currentStep?.team === 'blue' ? red : blue

  const availableLanes = useMemo(() => {
    const taken = currentTeamPicks.map((p) => p.lane)
    return ALL_LANES.filter((l) => !taken.includes(l))
  }, [currentTeamPicks])

  const excludedChampions = useMemo(
    () => [...banned.map((b) => b.champion), ...blue.map((p) => p.champion), ...red.map((p) => p.champion)],
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
    setBanned((prev) => [...prev, { champion, team: currentStep.team }])
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

  const handleModeChange = (newMode) => {
    setMode(newMode)
    handleReset()
  }

  const handleManualConfirm = (action) => {
    const resolved = resolve(inputValue)
    if (!resolved) {
      setError('목록에 있는 챔피언 이름을 정확히 선택해주세요 (한글/영문 둘 다 가능).')
      return
    }
    setError('')
    action(resolved)
  }

  const banSuggestions = topChampions.filter((c) => !excludedChampions.includes(c.champion)).slice(0, 8)

  return (
    <div className="container draft-container">
      <p className="subtitle">
        밴픽 순서를 따라가면서, 픽 차례마다 라인을 고르면 지금까지의 아군/적군 조합을 고려한 추정 승률로
        추천 챔피언을 보여줘요. 챔피언은 한글/영문 둘 다 검색할 수 있어요.
      </p>

      <div className="mode-select">
        {Object.entries(MODES).map(([key, m]) => (
          <button
            key={key}
            type="button"
            className={mode === key ? 'tab active' : 'tab'}
            onClick={() => handleModeChange(key)}
          >
            {m.label}
          </button>
        ))}
      </div>

      <div className="draft-status">
        {currentStep ? (
          <p>
            <strong>{stepIndex + 1}/{draftSequence.length}단계</strong> — {TEAM_LABELS[currentStep.team]}{' '}
            {currentStep.type === 'ban' ? '밴' : '픽'}
          </p>
        ) : (
          <p><strong>드래프트 완료</strong></p>
        )}
        <button type="button" onClick={handleReset} className="reset-button">처음부터</button>
      </div>

      <div className="draft-board">
        <TeamPanel
          label={`블루팀${currentStep?.team === 'blue' ? ' (진행중)' : ''}`}
          picks={blue}
          className="blue"
          displayName={displayName}
        />
        <TeamPanel
          label={`레드팀${currentStep?.team === 'red' ? ' (진행중)' : ''}`}
          picks={red}
          className="red"
          displayName={displayName}
        />
      </div>

      <div className="ban-list">
        <strong>밴:</strong>{' '}
        {banned.length
          ? banned.map((b, i) => (
              <span key={i} className={`ban-item ${b.team}`}>
                {displayName(b.champion)}
                <span className="ban-team-tag">({TEAM_LABELS[b.team]})</span>
                {i < banned.length - 1 ? ', ' : ''}
              </span>
            ))
          : '없음'}
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
            placeholder="직접 입력해서 픽 (한글/영문)"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
          />
          <button type="button" onClick={() => handleManualConfirm(confirmPick)} disabled={!inputValue}>
            이 챔피언으로 확정
          </button>
        </div>
      )}

      {currentStep?.type === 'ban' && (
        <div className="pick-controls">
          <input
            list="all-champion-list"
            placeholder="밴할 챔피언 입력 (한글/영문)"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
          />
          <button type="button" onClick={() => handleManualConfirm(confirmBan)} disabled={!inputValue}>
            밴 확정
          </button>
          <div className="ban-suggestions">
            <span>승률 상위 챔피언</span>
            <select value={banLane} onChange={(e) => setBanLane(e.target.value)}>
              {ALL_LANES.map((l) => (
                <option key={l} value={l}>{LANE_LABELS[l]}</option>
              ))}
            </select>
            {banSuggestions.map((c) => (
              <button key={c.champion} type="button" className="chip-button" onClick={() => confirmBan(c.champion)}>
                {displayName(c.champion)} ({c.win_rate}%)
              </button>
            ))}
          </div>
        </div>
      )}

      <datalist id="all-champion-list">
        {searchOptions.map((c) => (
          <option key={c.en} value={c.label} />
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
                    <td>{displayName(r.champion)}</td>
                    <td>{r.base_win_rate}%</td>
                    <td><strong>{r.estimated_win_rate}%</strong></td>
                    <td>{r.base_games}</td>
                    <td className="components-cell">
                      {r.components.slice(0, 3).map((c, idx) => (
                        <div key={idx} className={`component ${c.delta >= 0 ? 'positive' : 'negative'}`}>
                          {c.type === 'synergy' ? `+${displayName(c.with)}` : `vs ${displayName(c.vs)}`}: {c.delta > 0 ? '+' : ''}{c.delta}%p
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
