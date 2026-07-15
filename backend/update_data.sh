#!/bin/bash
# 솔로랭크 데이터를 다시 수집해서 DB를 최신 상태로 갱신하는 스크립트.
#
# 수동 실행:
#   ./update_data.sh
#
# 수집 규모 조절 (기본값: 소환사 50명, 소환사당 매치 20개):
#   MAX_SUMMONERS=100 MATCHES_PER_SUMMONER=20 ./update_data.sh
#
# 주기 실행(cron)에 등록하는 방법은 backend/README나 프로젝트 루트 README 참고.

set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') 실패: backend/.env 파일이 없습니다. RIOT_API_KEY를 먼저 설정하세요." >> update.log
  exit 1
fi

source venv/bin/activate

MAX_SUMMONERS="${MAX_SUMMONERS:-50}"
MATCHES_PER_SUMMONER="${MATCHES_PER_SUMMONER:-20}"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 업데이트 시작 (summoners=$MAX_SUMMONERS, matches=$MATCHES_PER_SUMMONER) ====="
  python3 -m app.collector --max-summoners "$MAX_SUMMONERS" --matches-per-summoner "$MATCHES_PER_SUMMONER"
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 업데이트 완료 ====="
} >> update.log 2>&1
