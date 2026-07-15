import { useEffect, useMemo, useState } from 'react'

// 챔피언 영문 ID 목록 + 한국어 이름 매핑을 가져와서, 한글/영문 어느 쪽으로
// 입력해도 실제 API에서 쓰는 영문 ID로 변환할 수 있게 해주는 훅.
export function useChampionNames() {
  const [champions, setChampions] = useState([])
  const [namesKo, setNamesKo] = useState({})
  const [images, setImages] = useState({})

  useEffect(() => {
    fetch('/api/champions').then((r) => r.json()).then(setChampions).catch(() => {})
    fetch('/api/champion-names').then((r) => r.json()).then(setNamesKo).catch(() => {})
    fetch('/api/champion-images').then((r) => r.json()).then(setImages).catch(() => {})
  }, [])

  const imageUrl = (enId) => images[enId] || null

  const koToEn = useMemo(() => {
    const map = {}
    for (const en of champions) {
      const ko = namesKo[en]
      if (ko) map[ko] = en
    }
    return map
  }, [champions, namesKo])

  const enSet = useMemo(() => new Set(champions), [champions])

  const displayName = (enId) => namesKo[enId] ? `${namesKo[enId]} (${enId})` : enId

  // 사용자가 입력한 문자열(한글 이름 or 영문 ID)을 실제 영문 ID로 변환.
  // 매칭되는 게 없으면 null.
  const resolve = (input) => {
    if (!input) return null
    const trimmed = input.trim()
    if (koToEn[trimmed]) return koToEn[trimmed]
    if (enSet.has(trimmed)) return trimmed
    // "이즈리얼 (Ezreal)" 형태로 표시된 값을 그대로 선택했을 때도 처리
    const match = trimmed.match(/\(([^)]+)\)\s*$/)
    if (match && enSet.has(match[1])) return match[1]
    return null
  }

  const searchOptions = useMemo(
    () => champions.map((en) => ({ en, label: displayName(en) })),
    [champions, namesKo],
  )

  return { champions, namesKo, koToEn, displayName, resolve, searchOptions, imageUrl }
}
