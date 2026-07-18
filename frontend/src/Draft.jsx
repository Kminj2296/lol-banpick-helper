import { useEffect, useMemo, useState } from 'react'
import ChampionThumb from './ChampionThumb'
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

const CANCEL_TITLE = '클릭하면 이 선택과 이후에 한 선택이 모두 취소돼요'
const SWAP_TITLE = '라인 스왑: 같은 팀에서 두 챔피언을 차례로 클릭하면 라인이 바뀌어요'

function TeamPanel({ label, picks, className, team, displayName, imageUrl, onCancel, swapSelection, onSwapClick }) {
  return (
    <div className={`team-panel ${className}`}>
      <h3>{label}</h3>
      <ul className="pick-list">
        {ALL_LANES.map((lane) => {
          const pick = picks.find((p) => p.lane === lane)
          const isSwapSelected = swapSelection?.team === team && swapSelection?.actionIndex === pick?.actionIndex
          return (
            <li key={lane}>
              <span className="lane-tag">{LANE_LABELS[lane]}</span>
              {pick ? (
                <span className="pick-row">
                  <button
                    type="button"
                    className="pick-champ cancelable"
                    title={CANCEL_TITLE}
                    onClick={() => onCancel(pick.actionIndex)}
                  >
                    <ChampionThumb src={imageUrl(pick.champion)} alt={displayName(pick.champion)} size={28} />
                    {displayName(pick.champion)}
                  </button>
                  <button
                    type="button"
                    className={`swap-button ${isSwapSelected ? 'active' : ''}`}
                    title={SWAP_TITLE}
                    onClick={() => onSwapClick(team, pick.actionIndex)}
                  >
                    ⇄
                  </button>
                </span>
              ) : (
                <span className="pick-champ">-</span>
              )}
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
  const [actions, setActions] = useState([]) // { type: 'ban'|'pick'|'skip', team, champion?, lane? }
  const [swapSelection, setSwapSelection] = useState(null) // { team, actionIndex } | null
  const [selectedLane, setSelectedLane] = useState('TOP')
  const [inputValue, setInputValue] = useState('')
  const [recommendations, setRecommendations] = useState([])
  const [loadingRec, setLoadingRec] = useState(false)
  const [error, setError] = useState('')
  const [liveEnabled, setLiveEnabled] = useState(false)
  const [liveConnected, setLiveConnected] = useState(false)
  const [patches, setPatches] = useState([])
  const [selectedPatch, setSelectedPatch] = useState('')
  const { displayName, resolve, searchOptions, imageUrl } = useChampionNames()

  const draftSequence = MODES[mode].sequence
  const stepIndex = actions.length

  useEffect(() => {
    fetch('/api/patches').then((r) => r.json()).then(setPatches).catch(() => {})
  }, [])

  useEffect(() => {
    const patchQuery = selectedPatch ? `&patches=${selectedPatch}` : ''
    fetch(`/api/top-champions?min_games=5&lane=${banLane}${patchQuery}`)
      .then((r) => r.json())
      .then(setTopChampions)
      .catch(() => {})
  }, [banLane, selectedPatch])

  useEffect(() => {
    if (!liveEnabled) {
      setLiveConnected(false)
      return
    }
    const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${wsProtocol}://${window.location.host}/ws/live`)
    ws.onopen = () => setLiveConnected(true)
    ws.onclose = () => setLiveConnected(false)
    ws.onerror = () => setLiveConnected(false)
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (Array.isArray(data.actions)) {
        setActions(data.actions)
        setSwapSelection(null)
      }
    }
    return () => ws.close()
  }, [liveEnabled])

  const banned = useMemo(
    () => actions.map((a, i) => ({ ...a, actionIndex: i })).filter((a) => a.type === 'ban'),
    [actions],
  )
  const blue = useMemo(
    () => actions.map((a, i) => ({ ...a, actionIndex: i })).filter((a) => a.type === 'pick' && a.team === 'blue'),
    [actions],
  )
  const red = useMemo(
    () => actions.map((a, i) => ({ ...a, actionIndex: i })).filter((a) => a.type === 'pick' && a.team === 'red'),
    [actions],
  )

  // 실시간 연동에서는 브리지가 "내 팀=blue"로 고정 태깅하는데, 실제 게임에서
  // 내 팀이 항상 먼저 행동하는(SOLOQ_SEQUENCE가 가정하는) 쪽이라는 보장은 없다.
  // 첫 실제 액션의 팀과 시퀀스가 가정한 팀이 다르면, 이후 모든 단계에서 라벨을 뒤집어
  // 아군/적군이 뒤바뀌어 추천되는 것을 막는다.
  const teamSwapped = useMemo(() => {
    if (actions.length === 0 || !draftSequence[0]) return false
    return actions[0].team !== draftSequence[0].team
  }, [actions, draftSequence])

  const currentStep = useMemo(() => {
    if (stepIndex >= draftSequence.length) return null
    const step = draftSequence[stepIndex]
    if (!teamSwapped) return step
    return { ...step, team: step.team === 'blue' ? 'red' : 'blue' }
  }, [stepIndex, draftSequence, teamSwapped])

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
        patches: selectedPatch ? [selectedPatch] : null,
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
  }, [currentStep, selectedLane, excludedChampions, selectedPatch])

  const confirmPick = (champion) => {
    if (!champion || !currentStep) return
    setActions((prev) => [...prev, { type: 'pick', team: currentStep.team, champion, lane: selectedLane }])
    setInputValue('')
  }

  const confirmBan = (champion) => {
    if (!champion || !currentStep) return
    setActions((prev) => [...prev, { type: 'ban', team: currentStep.team, champion }])
    setInputValue('')
  }

  const skipBan = () => {
    if (!currentStep) return
    setActions((prev) => [...prev, { type: 'skip', team: currentStep.team }])
    setInputValue('')
    setError('')
  }

  // actionIndex 시점 이후의 선택을 전부 되돌린다 (해당 액션 포함)
  const cancelFrom = (actionIndex) => {
    setActions((prev) => prev.slice(0, actionIndex))
    setInputValue('')
    setError('')
    setSwapSelection(null)
  }

  const handleSwapClick = (team, actionIndex) => {
    if (!swapSelection || swapSelection.team !== team) {
      setSwapSelection({ team, actionIndex })
      return
    }
    if (swapSelection.actionIndex === actionIndex) {
      setSwapSelection(null)
      return
    }
    setActions((prev) => {
      const next = [...prev]
      const laneA = next[swapSelection.actionIndex].lane
      const laneB = next[actionIndex].lane
      next[swapSelection.actionIndex] = { ...next[swapSelection.actionIndex], lane: laneB }
      next[actionIndex] = { ...next[actionIndex], lane: laneA }
      return next
    })
    setSwapSelection(null)
  }

  const handleReset = () => {
    setActions([])
    setInputValue('')
    setRecommendations([])
    setSwapSelection(null)
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
        추천 챔피언을 보여줘요. 챔피언은 한글/영문 둘 다 검색할 수 있어요. 위에 올라간 픽/밴을 다시 누르면
        그 선택과 그 뒤에 한 선택이 모두 취소돼요. 픽 옆의 ⇄ 버튼을 누르면 같은 팀 안에서 두 챔피언의
        라인을 바꿀 수 있어요.
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

      {patches.length > 0 && (
        <div className="patch-select">
          <label htmlFor="patch-filter">패치 필터</label>
          <select id="patch-filter" value={selectedPatch} onChange={(e) => setSelectedPatch(e.target.value)}>
            <option value="">전체 패치 사용</option>
            {patches.map((p) => (
              <option key={p.patch} value={p.patch}>{p.patch} ({p.games}경기)</option>
            ))}
          </select>
        </div>
      )}

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

      <div className="live-toggle">
        <label>
          <input
            type="checkbox"
            checked={liveEnabled}
            onChange={(e) => {
              setLiveEnabled(e.target.checked)
              if (e.target.checked) {
                setMode('soloq') // 실시간 연동은 실제 솔로랭크 밴픽 순서만 지원
                handleReset()
              }
            }}
          />
          {' '}실시간 연동 (PC에서 로컬 브리지 실행 중이어야 해요)
        </label>
        {liveEnabled && (
          <span className={`live-status ${liveConnected ? 'on' : 'off'}`}>
            {liveConnected ? '연결됨 · 게임 클라이언트 대기 중' : '연결 중...'}
          </span>
        )}
      </div>

      <div className="draft-board">
        <TeamPanel
          label={`블루팀${currentStep?.team === 'blue' ? ' (진행중)' : ''}`}
          picks={blue}
          className="blue"
          team="blue"
          displayName={displayName}
          imageUrl={imageUrl}
          onCancel={cancelFrom}
          swapSelection={swapSelection}
          onSwapClick={handleSwapClick}
        />
        <TeamPanel
          label={`레드팀${currentStep?.team === 'red' ? ' (진행중)' : ''}`}
          picks={red}
          className="red"
          team="red"
          displayName={displayName}
          imageUrl={imageUrl}
          onCancel={cancelFrom}
          swapSelection={swapSelection}
          onSwapClick={handleSwapClick}
        />
      </div>

      <div className="ban-list">
        <strong>밴:</strong>{' '}
        {banned.length
          ? banned.map((b) => (
              <button
                key={b.actionIndex}
                type="button"
                className={`ban-item ${b.team}`}
                title={CANCEL_TITLE}
                onClick={() => cancelFrom(b.actionIndex)}
              >
                <ChampionThumb src={imageUrl(b.champion)} alt={displayName(b.champion)} size={20} />
                {displayName(b.champion)}
                <span className="ban-team-tag">({TEAM_LABELS[b.team]})</span>
              </button>
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
          {!liveEnabled && (
            <>
              <input
                list="all-champion-list"
                placeholder="직접 입력해서 픽 (한글/영문)"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
              />
              <button type="button" onClick={() => handleManualConfirm(confirmPick)} disabled={!inputValue}>
                이 챔피언으로 확정
              </button>
            </>
          )}
        </div>
      )}

      {currentStep?.type === 'ban' && !liveEnabled && (
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
          <button type="button" onClick={skipBan} className="skip-button">
            밴 없이 넘어가기
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
                <ChampionThumb src={imageUrl(c.champion)} alt={displayName(c.champion)} size={20} />
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
            <>
              <p className="table-note">
                <strong>기본 승률</strong>: 이 챔피언 단독 승률 (다른 픽/밴 고려 안 함, 표본 보정 전 원본 값) ·{' '}
                <strong>추정 승률</strong>: 표본이 적으면 이 라인 평균 쪽으로 당겨서 보정한 기본 승률에
                지금까지 픽한 아군과의 시너지, 상대 챔피언과의 카운터, 이 라인에서 실제로 얼마나 자주
                픽되는지(라인 적합도) 보정치를 더한 값 ·{' '}
                <strong>추정 승률이 높은 순</strong>으로 정렬돼요.
              </p>
              <div className="table-scroll">
              <table className="result-table">
                <thead>
                  <tr>
                    <th>순위</th>
                    <th>챔피언</th>
                    <th title="이 챔피언 단독 승률 (다른 픽/밴 고려 안 함)">기본 승률</th>
                    <th title="기본 승률 + 아군 시너지 + 상대 카운터 보정치">추정 승률</th>
                    <th>표본</th>
                    <th>근거</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {recommendations.map((r, i) => (
                    <tr key={r.champion}>
                      <td>{i + 1}</td>
                      <td className="champion-cell">
                        <ChampionThumb src={imageUrl(r.champion)} alt={displayName(r.champion)} size={28} />
                        <span className="champion-name" title={displayName(r.champion)}>{displayName(r.champion)}</span>
                      </td>
                      <td>{r.base_win_rate}%</td>
                      <td><strong>{r.estimated_win_rate}%</strong></td>
                      <td>{r.base_games}</td>
                      <td className="components-cell">
                        {r.components.slice(0, 3).map((c, idx) => (
                          <div key={idx} className={`component ${c.delta >= 0 ? 'positive' : 'negative'}`}>
                            {c.type === 'synergy' && `+${displayName(c.with)}`}
                            {c.type === 'counter' && `vs ${displayName(c.vs)}`}
                            {c.type === 'lane_fit' && `라인 적합도 (${c.lane_share}%)`}
                            {c.type === 'sample_adjust' && `표본 보정 (${c.games}게임)`}
                            : {c.delta > 0 ? '+' : ''}{c.delta}%p
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
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

export default Draft
