# 📌 Auto Trading System
 
> 한국투자증권(KIS) API 기반 비동기 자동매매 시스템  
> FastAPI + Celery + PostgreSQL + Redis
 
---
 
## 📖 목차
 
1. [프로젝트 소개](#-프로젝트-소개)
2. [기술 스택](#️-기술-스택)
3. [프로젝트 구조](#-프로젝트-구조)
4. [시스템 아키텍처](#️-시스템-아키텍처)
5. [핵심 모듈 상세](#-핵심-모듈-상세)
   - [주문 처리 파이프라인 (Worker)](#-주문-처리-파이프라인-worker)
   - [주문 상태 머신](#-주문-상태-머신)
   - [부모-자식 주문 관계](#-부모-자식-주문-관계)
   - [실시간 시세 및 WebSocket](#-실시간-시세-및-websocket)
   - [매매 전략 모듈](#-매매-전략-모듈)
   - [리스크 관리 (Safety)](#️-리스크-관리-safety)
6. [API 엔드포인트](#-api-엔드포인트)
7. [실행 방법](#-실행-방법)
8. [환경 변수](#-환경-변수)
9. [테스트](#-테스트)
10. [주의사항](#️-주의사항)
 
---
 
## 🎯 프로젝트 소개
 
본 시스템은 **한국투자증권(KIS) Open API**를 활용한 국내 주식 자동매매 플랫폼입니다.
 
주문 실행과 상태 추적을 **완전히 분리된 비동기 워커 파이프라인**으로 처리하며,  
실시간 시세 수신, 매매 전략 실행, 백테스팅까지 통합된 구조를 갖추고 있습니다.
 
### 주요 특징
 
- 🔄 **3-Worker 비동기 파이프라인** — 주문 제출 / 상태 추적 / 복구를 각각 독립 워커로 처리
- 📊 **실시간 시세** — KIS WebSocket 기반 실시간 체결가 수신
- 🧠 **전략 모듈** — 스크리너 → 전략 실행 → 시그널 생성의 2단계 구조
- 🛡️ **안전 장치** — Kill Switch, 상태 머신 검증, Rate Limit 자동 재시도
- 🐳 **Docker 배포** — 멀티 컨테이너 구성으로 즉시 배포 가능
- 📡 **실시간 모니터링** — WebSocket + Redis Pub/Sub 기반 주문 상태 브로드캐스트
 
---
 
## 🛠️ 기술 스택
 
| 분류 | 기술 |
|------|------|
| **Framework** | FastAPI, Uvicorn, Pydantic |
| **Database** | PostgreSQL, SQLAlchemy (Async), Alembic |
| **Message Queue** | Celery, Redis |
| **실시간 통신** | WebSocket, Redis Pub/Sub |
| **HTTP Client** | httpx (Async) |
| **데이터 분석** | Pandas, NumPy, Backtesting.py, Matplotlib |
| **시장 데이터** | Finance DataReader, DART API |
| **로깅** | Loguru |
| **배포** | Docker Compose |
| **테스트** | pytest, pytest-asyncio, respx |
| **Language** | Python 3.12+ |
 
---
 
## 📁 프로젝트 구조
 
```
app/
├── api/                    # 🌐 FastAPI 라우터
│   ├── router.py           #    메인 라우터
│   ├── router_account.py   #    계좌 조회 API
│   ├── router_order.py     #    주문 생성 API (매수/매도/정정/취소)
│   ├── router_order_query.py #  주문 조회 API
│   ├── router_realtime.py  #    실시간 시세 구독 API
│   └── router_safety.py    #    Kill Switch API
│
├── broker/kis/             # 🏦 한국투자증권 API 연동
│   ├── kis_auth.py         #    인증 및 토큰 관리
│   ├── kis_order.py        #    주문 실행 (매수/매도/정정/취소)
│   ├── kis_account.py      #    계좌 및 잔고 조회
│   ├── kis_client.py       #    HTTP 클라이언트 래퍼
│   └── enums.py            #    KIS 전용 상수 (TRID, 주문구분 등)
│
├── core/                   # ⚙️ 핵심 설정
│   ├── settings.py         #    환경 설정 (Pydantic Settings)
│   ├── enums.py            #    주문 상태/종류/방향 Enum
│   ├── constants.py        #    상수 정의
│   └── exceptions.py       #    커스텀 예외
│
├── db/                     # 🗄️ 데이터베이스
│   ├── models/
│   │   ├── order.py        #    주문 모델
│   │   └── order_event.py  #    주문 이벤트 감사 추적 모델
│   └── session.py          #    Async DB 세션 관리
│
├── domain/                 # 🧩 도메인 로직
│   └── order_state.py      #    주문 상태 머신 (전이 규칙)
│
├── market/                 # 📈 시장 데이터
│   ├── provider/
│   │   ├── fdr_provider.py #    Finance DataReader 연동
│   │   └── dart_provider.py#    DART 재무제표 API 연동
│   └── realtime/
│       └── kis_realtime_client.py  # KIS WebSocket 실시간 클라이언트
│
├── repository/             # 💾 데이터 접근 계층
│   ├── order_repository.py #    주문 CRUD
│   └── order_event_repository.py # 이벤트 CRUD
│
├── schemas/                # 📋 요청/응답 스키마 (Pydantic)
│   ├── kis/                #    KIS API 스키마
│   ├── safety/             #    Kill Switch 스키마
│   └── strategy/           #    백테스트 스키마
│
├── services/               # 🔧 비즈니스 서비스
│   ├── kis/
│   │   ├── auth_service.py #    토큰 관리 (Redis 캐싱)
│   │   ├── trade_service.py#    주문 처리 서비스
│   │   └── account_service.py #  계좌 정보 서비스
│   └── safety/
│       └── kill_switch_service.py # 긴급 거래 중지
│
├── strategy/               # 🧠 매매 전략 모듈
│   ├── screener/           #    종목 스크리너 (F-Score 등)
│   ├── filter/             #    밸류에이션 필터
│   ├── strategies/         #    매매 전략 (MA Cross, RSI)
│   ├── backtest/           #    백테스팅 프레임워크
│   └── runtime/            #    실시간 전략 실행기
│
├── websocket/              # 📡 실시간 통신
│   ├── publisher.py        #    Redis Pub/Sub 발행
│   ├── subscriber.py       #    이벤트 구독
│   ├── manager.py          #    WebSocket 연결 관리
│   ├── order_ws.py         #    주문 WebSocket 엔드포인트
│   └── serializers.py      #    직렬화
│
├── worker/                 # 👷 Celery 워커
│   ├── celery_app.py       #    Celery 앱 설정
│   ├── tasks_order.py      #    Worker 1: 주문 제출
│   ├── tasks_order_status.py #  Worker 2: 상태 추적
│   └── tasks_recovery.py   #    Worker 3: 복구
│
└── main.py                 # 🚀 FastAPI 앱 엔트리포인트
```
 
---
 
## 🏛️ 시스템 아키텍처
 
### 🔄 전체 처리 흐름
 
![architecture](README_IMG/sequence_diagram.png)
 
> **[Client/API]** → **[DB 주문 생성]** → **[Worker 1 - 주문 실행]** → **[Broker API]** → **[Worker 2 - 상태 추적]** → **[DB 상태 업데이트]**
 
시스템의 핵심 설계 원칙은 **주문 실행과 상태 처리의 완전한 분리**입니다.
 
| 단계 | 담당 | 설명 |
|------|------|------|
| 1️⃣ 주문 생성 | API Server | 클라이언트 요청 → DB에 `PENDING` 상태로 저장 |
| 2️⃣ 주문 실행 | Worker 1 | DB에서 주문 조회 → KIS Broker API 호출 |
| 3️⃣ 상태 추적 | Worker 2 | Broker 체결 조회 → 적응형 폴링으로 최종 상태까지 추적 |
| 4️⃣ 복구 | Worker 3 | 장애 복구, 미체결 주문 정리 |
 
---
 
### ⏱️ 적응형 폴링 전략
 
![polling](README_IMG/Polling_and_Retry_다이어그램.png)
 
Worker 2는 **aggressive polling + adaptive backoff + low-frequency polling**을 조합하여 주문 상태를 추적합니다.
 
| 구간 | 시간 범위 | 폴링 간격 | 설명 |
|------|-----------|-----------|------|
| 🟢 Fast Window | 0 ~ 90초 | 1 ~ 15초 | 체결 직후 빠른 상태 확인 |
| 🟡 Slow Window | 90초 ~ 30분 | 60초 | 장기 미체결 주문 모니터링 |
| 🔴 Timeout | 30분 초과 | - | 추적 중단, 상태 정리 |
 
---
 
## 🔍 핵심 모듈 상세
 
### 👷 주문 처리 파이프라인 (Worker)
 
#### Worker 1 — 주문 제출 (`orders.submit` 큐)
 
"**실행만 담당하는 워커**" — 비즈니스 로직 없음, 상태 판단 없음
 
1. DB에서 주문 조회 및 `PENDING` 상태 확인
2. `PROCESSING` 상태로 전환
3. Redis 캐싱된 KIS 인증 토큰 획득
4. **Kill Switch 확인** (활성화 시 주문 차단)
5. 주문 종류에 따라 Broker API 호출:
   - `NEW` → `buy_domestic_stock()` / `sell_domestic_stock()`
   - `MODIFY` → `revise_domestic_stock()`
   - `CANCEL` → `cancel_domestic_stock()`
6. 응답 파싱 후 `ACCEPTED` / `REQUESTED` / `FAILED` 상태 전환
7. Worker 2로 상태 추적 태스크 전달
 
#### Worker 2 — 상태 추적 (`orders.track` 큐)
 
"**상태 머신 + 정합성 관리자**" — 모든 상태 결정을 담당
 
| 주문 타입 | 처리 내용 |
|----------|----------|
| BUY / SELL | 체결 상태 업데이트 (FILLED / PARTIAL_FILLED) |
| CANCEL | 자기 상태 + 원주문 `remaining_qty` 반영 (delta 기반) |
| MODIFY | 자기 상태 + 원주문 `filled_qty` 반영 (delta 기반) |
 
#### Worker 3 — 복구 (`orders.recovery` 큐)
 
- 앱 재시작 시 미완료 주문 복구
- Stale 주문 탐지 및 정리
 
---
 
### 🔀 주문 상태 머신
 
주문은 아래 상태 전이 규칙을 엄격히 따릅니다. 잘못된 전이는 차단됩니다.
 
```
PENDING ──→ PROCESSING ──→ REQUESTED ──→ ACCEPTED ──→ PARTIAL_FILLED ──→ FILLED
   │            │              │            │                              (종료)
   │            │              │            ├──→ FILLED
   │            │              │            ├──→ CANCELED
   │            │              │            └──→ FAILED
   │            │              ├──→ PARTIAL_FILLED
   │            │              ├──→ FILLED
   │            │              ├──→ CANCELED
   │            │              └──→ FAILED
   │            ├──→ ACCEPTED
   │            ├──→ FAILED
   │            └──→ PENDING (Rate Limit 재시도)
   └──→ FAILED
```
 
**종료 상태 (Terminal States):** `FILLED`, `CANCELED`, `FAILED`
 
#### 📌 상태 판정 기준
 
| 조건 | 상태 |
|------|------|
| `remaining_qty == 0` + 체결 있음 | ✅ `FILLED` |
| `remaining_qty > 0` + 체결 있음 | 🔶 `PARTIAL_FILLED` |
| `remaining_qty == 0` + 체결 없음 | ❌ `CANCELED` |
| 오류 발생 | 🚫 `FAILED` |
 
---
 
### 👪 부모-자식 주문 관계
 
![parent-child](README_IMG/Parent_Child_관계_다이어그램.png)
 
**부모-자식 주문 관계 다이어그램**

 ![sequence](README_IMG/자식_주문_포함_시퀀스.png){: width="25%" height="25%"}
 
**자식 주문 포함 시퀀스 다이어그램**
 
#### 개념
 
| 구분 | 설명 | 예시 |
|------|------|------|
| **부모 주문** | 최초 매수/매도 (NEW) | 삼성전자 100주 매수 |
| **자식 주문** | 부모를 정정/취소하는 주문 | 위 주문을 50주로 정정 |
 
#### 🔑 delta_qty — 중복 반영 방지의 핵심
 
Broker는 **누적 체결 수량**을 반환합니다. 따라서 반드시 **delta(변화량) 기준**으로만 부모 주문에 반영해야 합니다.
 
```
예시:
  이전 조회: filled_qty = 2
  현재 조회: filled_qty = 5
  → delta = 3 (이번에 새로 체결된 수량)
  → 부모 주문에 delta 3만 반영
```
 
#### 자식 → 부모 영향 규칙
 
| 자식 유형 | 부모에 미치는 영향 | 부모 상태 변화 |
|----------|------------------|---------------|
| **MODIFY** | `remaining_qty` 감소 또는 유지 | 정정 결과에 따라 재판정 |
| **CANCEL** | `remaining_qty` 감소 | 잔량 0 시 `CANCELED` |
 
> ⚠️ **핵심 원칙:** 부모 주문 상태는 항상 **부모 자신의 수량 기준**으로만 판단합니다.  
> 자식 주문은 부모의 수량을 변경할 뿐, 상태를 직접 결정하지 않습니다.
 
---
 
### 📡 실시간 시세 및 WebSocket
 
#### 실시간 시세 수신
 
- KIS WebSocket API를 통해 **실시간 체결가(H0STCNT0)** 수신
- 종목 단위 구독/해제 방식
- 자동 재연결 (최대 10회, 3초 간격 backoff)
 
#### 주문 상태 실시간 브로드캐스트
 
```
Worker 주문 업데이트
    → Redis Pub/Sub (order_updates 채널)
        → Subscriber 수신
            → WebSocket Manager
                → 연결된 클라이언트에 브로드캐스트
```
 
- **엔드포인트:** `ws://localhost:8000/ws/orders`
- Worker가 주문 상태를 변경할 때마다 연결된 모든 클라이언트에 실시간 전달
 
---
 
### 🧠 매매 전략 모듈
 
전략 모듈은 **2단계 구조**로 설계되어 있습니다.
 
| 단계 | 역할 | 구현 |
|------|------|------|
| **1단계: 종목 선정** | 오늘 어떤 종목을 볼 것인가 | Screener (F-Score), Filter (Valuation) |
| **2단계: 매매 실행** | 지금 이 종목을 살 것인가 / 팔 것인가 | Strategy (MA Cross, RSI) |
 
#### 구현된 전략 컴포넌트
 
| 컴포넌트 | 설명 |
|----------|------|
| **F-Score Screener** | 재무지표 기반 종목 스크리닝 (DART API 연동) |
| **Valuation Filter** | PER, PBR 등 밸류에이션 기반 필터링 |
| **MA Cross Strategy** | 이동평균 골든크로스/데드크로스 기반 매매 신호 |
| **RSI Strategy** | RSI 과매수/과매도 기반 매매 신호 |
| **Backtest Runner** | 과거 데이터 기반 전략 검증 (수익률, 드로다운 분석, 시각화) |
| **Runtime Executor** | 실시간 전략 실행기 |
 
> 📚 **전략 모듈의 상세 설계 문서는 [Strategy README](app/strategy/README.md)를 참조하세요.**
 
---
 
### 🛡️ 리스크 관리 (Safety)
 
#### Kill Switch — 긴급 거래 중지
 
Redis 기반의 글로벌 거래 차단 스위치입니다.
 
| 기능 | 설명 |
|------|------|
| `turn_on()` | 🔴 모든 신규 주문 즉시 차단 |
| `turn_off()` | 🟢 주문 차단 해제 |
| `is_on()` | 현재 Kill Switch 상태 확인 |
 
- Worker 1이 주문 제출 전 **매번 Kill Switch 상태를 확인**
- 활성화 시 신규 주문은 차단되지만, 이미 진행 중인 상태 추적은 계속됨
 
#### 추가 안전 장치
 
| 장치 | 설명 |
|------|------|
| **상태 머신 검증** | 허용되지 않은 상태 전이 차단 |
| **Rate Limit 대응** | KIS API `EGW00201` 오류 감지 시 자동 재시도 (PROCESSING → PENDING) |
| **이벤트 감사 추적** | 모든 주문 상태 변경을 `OrderEvent` 테이블에 기록 |
 
---
 
## 🌐 API 엔드포인트
 
| 라우터 | 경로 | 주요 기능 |
|--------|------|-----------|
| 📋 **Account** | `/account` | 계좌 정보, 보유 종목, 잔고 조회 |
| 📝 **Order** | `/order` | 매수, 매도, 정정, 취소 주문 생성 |
| 🔍 **Order Query** | `/order-query` | 주문 내역 및 상세 조회 |
| 🛡️ **Safety** | `/safety` | Kill Switch ON/OFF 관리 |
| 📡 **Realtime** | `/realtime` | 실시간 시세 구독/해제 |
| 🔌 **WebSocket** | `ws://host/ws/orders` | 실시간 주문 상태 수신 |
 
> 📄 Swagger UI: `http://localhost:8000/docs`
 
---
 
## 🚀 실행 방법
 
### 1. 환경 설정
 
```bash
# 의존성 설치
poetry install
 
# 환경 변수 설정
cp .env.example .env
# .env 파일에 KIS API 키, DB 정보 등 입력
```
 
### 2. 로컬 실행
 
```bash
# API 서버 실행
poetry run uvicorn app.main:app --reload
 
# Celery Worker 실행 (터미널 3개)
poetry run celery -A app.worker.celery_app.celery_app worker --loglevel=info -Q orders.submit    # Worker 1
poetry run celery -A app.worker.celery_app.celery_app worker --loglevel=info -Q orders.track     # Worker 2
poetry run celery -A app.worker.celery_app.celery_app worker --loglevel=info -Q orders.recovery  # Worker 3
```
 
> ⚠️ Windows 환경에서는 Celery 실행 시 `--pool=solo` 옵션을 추가해야 합니다.
 
### 3. Docker 실행 (권장)
 
```bash
# 전체 서비스 실행
docker compose up --build
 
# 백그라운드 실행
docker compose up -d --build
 
# 로그 확인
docker compose logs -f            # 전체 로그
docker compose logs -f api        # API 서버만
docker compose logs -f worker_1   # Worker 1만
docker compose logs -f worker_2   # Worker 2만
```
 
#### Docker 서비스 구성
 
| 서비스 | 컨테이너 | 역할 | 포트 |
|--------|----------|------|------|
| `redis` | autotrading-redis | 메시지 브로커 / 캐시 | 6380 |
| `api` | autotrading-api | FastAPI 서버 | 8000 |
| `worker_1` | autotrading-worker-1 | 주문 제출 (orders.submit) | - |
| `worker_2` | autotrading-worker-2 | 상태 추적 (orders.track) | - |
| `worker_3` | autotrading-worker-3 | 복구 작업 (orders.recovery) | - |
 
---
 
## 🔐 환경 변수
 
`.env` 파일에 다음 항목을 설정합니다.
 
```bash
# 🔧 Application
APP_ENV=local                    # local / development / production
TRADING_ENV=paper                # paper(모의투자) / live(실전투자)
 
# 🏦 KIS API
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_AUTH_USER=your_user_id
KIS_AUTH_PASSWORD=your_password
KIS_ACCOUNT_NO=your_account_no
KIS_ACCOUNT_PRODUCT_CODE=01
 
# 🗄️ Database (PostgreSQL)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your_password
 
# 📮 Redis / Celery
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
 
# 📊 DART API
DART_API_KEY=your_dart_api_key
```
 
> ⚠️ Docker 환경에서는 `localhost` 대신 서비스명을 사용합니다.  
> Redis → `redis:6379` / 외부 DB → `host.docker.internal`
 
---
 
## 🧪 테스트
 
```bash
# 로컬 테스트 실행
poetry run pytest -v
 
# Docker 테스트 실행
docker compose build test_runner
docker compose run --rm test_runner
 
# 커버리지 포함
poetry run pytest --cov=app -v
```
 
---
 
## ⚠️ 주의사항
 
| 항목 | 설명 |
|------|------|
| 🪟 Windows Celery | `--pool=solo` 옵션 필수 |
| 🐳 Docker 호스트 | `localhost` 대신 서비스명 또는 `host.docker.internal` 사용 |
| 🔑 모의/실전 전환 | `.env`의 `TRADING_ENV` 값만 변경 (`paper` ↔ `live`) |
| 🚫 Kill Switch | 활성화 시 모든 신규 주문이 차단됨 — 해제 전까지 매매 불가 |
| 📡 실시간 데이터 | KIS WebSocket은 종목 단위 구독 방식 — 전 종목 동시 감시 불가 |
 
