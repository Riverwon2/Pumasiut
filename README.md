# 곁 — 생활지원 연결 에이전트 데모

자연어 생활지원 요청을 최대 3개의 작업으로 분리하고, 매일 반복되는 가능 시간대와
거리·도움 완료 횟수를 기준으로 서로 다른 도우미를 추천하는 라이브 데모입니다.

## 구성

- `frontend/`: React, TypeScript, Vite 기반 50:50 요청자·도우미 화면
- `backend/`: FastAPI와 OpenAI Agents SDK 기반 요청 분석·SSE 스트리밍
- `backend/data/helper-users.json`: 데모 도우미 12명
- `backend/tests/`: 시간대·순위·중복 방지·입력 계약 테스트
- `docs/architecture.md`: 확정된 프로토타입 아키텍처

추천 계산은 모델이 아닌 Python 코드에서 수행합니다. 모델은 요청을 1~3개 작업으로
분리하며, UI에서 선택한 날짜와 시간이 자연어보다 우선합니다.

## 환경변수

저장소 루트의 기존 `.env`를 사용합니다.

```dotenv
OPENAI_API_KEY=...
OPENAI_MODEL=...
FRONTEND_ORIGIN=http://localhost:5173
```

`.env`는 Git에서 제외되며 API 키는 백엔드에서만 사용합니다.

## 실행

PowerShell 창 1:

```powershell
cd backend
$env:UV_CACHE_DIR = (Join-Path (Get-Location) '.uv-cache')
uv sync --python 'C:\Program Files\Python311\python.exe'
uv run python main.py
```

PowerShell 창 2:

```powershell
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173`을 엽니다. 백엔드 상태 확인 주소는
`http://127.0.0.1:8000/health`입니다.

## 검증

```powershell
cd backend
$env:UV_CACHE_DIR = (Join-Path (Get-Location) '.uv-cache')
uv run ruff check .
uv run pytest -q

cd ..\frontend
npm test
npm run build
```

## 데모 범위

- 작업당 서로 다른 도우미 1명, 작업과 도우미 모두 최대 3개
- 작업마다 후보를 최대 2명까지 순차 제안
- 거부 시 다음 후보를 표시하고, 두 후보가 모두 거부하면 `지원자 없음`으로 종료
- 재추천, 실제 알림, 로그인, 데이터베이스, 지도 연동은 제외
- 좌측 처리 창에는 공개 단계 요약만 표시하고 모델의 내부 사고과정은 표시하지 않음
