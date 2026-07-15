# 롤 밴픽 도우미

밴픽 순서(솔로랭크 방식/대회 방식 선택 가능)를 따라가면서, 픽 차례마다 지금까지의 아군/적군
조합을 고려해 승률이 높은 챔피언을 추천해주는 웹앱입니다. 챔피언은 한글/영문 아무거나 검색할 수
있습니다. 라인 1대1 카운터 픽 검색 기능도 별도로 있습니다.

lol.ps 같은 스크래핑 사이트 대신, **Riot 공식 API로 챌린저/그랜드마스터 랭크 게임 데이터를 직접 수집**해서
경기당 10명 전원의 팀/라인/챔피언/승패를 자체 집계합니다. Oracle's Elixir CSV를 통해 LCK 등 프로 대회
데이터도 추가로 넣을 수 있습니다.

## 승률 계산 방식

정확히 같은 10챔피언 조합이 다시 나올 확률은 사실상 0이라, "이 조합의 승률"을 직접 셀 수는 없습니다.
대신 다음을 더하는 **가법(additive) 모델**을 씁니다:

```
추정 승률 = 개별 챔피언 기본 승률
          + Σ (같은 팀 챔피언과 함께일 때 승률 - 기본 승률)   ← 시너지
          + Σ (상대 챔피언과 맞붙을 때 승률 - 기본 승률)      ← 카운터
```

표본이 적은 매치업(예: 2게임 100%)이 그대로 반영되지 않도록, 표본 수에 비례해 보정치를 줄이는
축소(shrinkage) 가중치를 곱합니다 (`app/scorer.py`의 `shrinkage_k`). 나중에 로지스틱 회귀 등
다른 모델로 바꾸더라도 API 응답 형태는 그대로 유지되도록 `scorer.py`에 계산 로직을 분리해뒀습니다.

## 구조

- `backend/` — FastAPI 서버 + 매치 수집 스크립트 + SQLite
- `frontend/` — React(Vite) 웹앱

## 1. Riot API 키 발급

1. https://developer.riotgames.com/ 에서 라이엇 계정으로 로그인 (계정이 없으면 직접 가입해야 합니다)
2. 로그인 후 대시보드에서 "Personal API Key" 발급 (24시간마다 만료되어 재발급 필요)
3. `backend/.env.example`을 `backend/.env`로 복사하고 키를 채워넣기

```bash
cd backend
cp .env.example .env
# .env 파일 열어서 RIOT_API_KEY=발급받은키 로 수정
```

## 2. 백엔드 실행

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 데이터 수집 (챌린저/그마 소환사 20명 기준 매치 수집, 시간 좀 걸림)
python -m app.collector --max-summoners 20 --matches-per-summoner 10

# API 서버 실행
uvicorn app.main:app --reload --port 8000
```

`app.collector`는 Riot API 개인 키의 요청 제한(2분당 100회)에 맞춰 자동으로 속도를 조절합니다.
더 많은 데이터가 필요하면 `--max-summoners`, `--matches-per-summoner` 값을 늘려서 여러 번 실행하면 됩니다
(이미 처리한 매치는 건너뜁니다).

## 2-1. (선택) LCK 등 프로 대회 데이터 추가

Riot 공식 API에는 e스포츠 경기 기록이 없어서, 커뮤니티가 관리하는
[Oracle's Elixir](https://oracleselixir.com/tools/downloads)에서 CSV를 받아 넣습니다.

1. 위 페이지에서 원하는 시즌의 CSV를 다운로드
2. 아래 명령으로 적재 (LCK만 넣고 싶으면 `--league LCK`, 전체는 생략)

```bash
cd backend
source venv/bin/activate
python -m app.load_pro_data --csv ~/Downloads/2025_LoL_esports_match_data.csv --league LCK
```

솔로랭크 데이터와 프로 데이터는 `source` 컬럼(`soloq` / `pro:LCK`)으로 구분되어 같이 쌓입니다.
`/api/draft/recommend` 호출 시 `sources` 값을 지정하면 특정 소스만 골라서 계산할 수 있습니다.

## 3. 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173` 접속. `/api` 요청은 Vite 프록시를 통해 `localhost:8000` 백엔드로 전달됩니다.

## 밴픽 순서

프론트에서 두 가지 순서 중 골라서 진행할 수 있습니다:

- **솔로랭크 순서**: 밴 10개(양팀 번갈아 5개씩) → 픽 10개(1-2-2-2-2-1 스네이크)
- **대회 순서**: 밴 6개(B-R-B-R-B-R) → 픽 6개(B-R-R-B-B-R) → 밴 4개(R-B-R-B) → 픽 4개(R-B-B-R)

## API

- `GET /api/lanes` — 라인 목록
- `GET /api/champions` — 수집된 챔피언 목록 (영문 ID)
- `GET /api/champion-names` — 챔피언 영문 ID → 한국어 이름 매핑 (Riot Data Dragon 기준,
  `backend/app/data/champion_names_ko.json`)
- `GET /api/champion-images` — 챔피언 영문 ID → 썸네일 이미지 URL 매핑 (Riot Data Dragon CDN,
  `backend/app/data/champion_images.json`)
- `GET /api/sources` — 적재된 데이터 소스 목록 (soloq, pro:LCK 등)과 경기 수
- `GET /api/top-champions?min_games=5&sources=soloq` — 라인 구분 없는 전체 챔피언 승률 순위 (밴 추천용)
- `GET /api/recommend?lane=TOP&enemy_champion=Darius&min_games=5` — 같은 라인 1대1 상대 기준 카운터 픽
- `POST /api/draft/recommend` — 드래프트 상태를 받아 다음 픽 추천
  ```json
  {
    "lane": "TOP",
    "allies": ["Leona"],
    "enemies": ["Jinx"],
    "banned": ["Azir"],
    "min_games": 5,
    "sources": null
  }
  ```
