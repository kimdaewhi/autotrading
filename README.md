# 📌 Auto Trading System

비동기 워커 기반으로 주문 실행과 상태 추적을 분리한 자동매매 백엔드입니다.  
핵심 목표는 **주문 정합성(Consistency)**, **확장성(Scalability)**, **운영 안정성(Reliability)** 입니다.

---

## 🧭 목차

- [✨ 프로젝트 한눈에 보기](#-프로젝트-한눈에-보기)
- [🏗️ 핵심 구조 개요](#️-핵심-구조-개요)
- [⚙️ Worker 역할 상세](#️-worker-역할-상세)
- [🔥 핵심 도메인 개념](#-핵심-도메인-개념)
- [🧪 실행 환경 구축](#-실행-환경-구축)
- [🔐 환경 변수](#-환경-변수)
- [🚀 실행 가이드](#-실행-가이드)
- [🧷 운영 시 주의사항](#-운영-시-주의사항)
- [📚 전략(Strategy) 모듈 문서](#-전략strategy-모듈-문서)

---

## ✨ 프로젝트 한눈에 보기

### 이 프로젝트는 어떤 문제를 해결하나요?

주문 처리 시스템에서는 다음 문제가 자주 발생합니다.

- 주문 요청은 성공했지만 체결 상태 반영이 늦는 문제
- 재시도 과정에서 체결 수량이 중복 반영되는 문제
- 정정/취소 주문이 원주문(부모 주문) 상태와 충돌하는 문제

본 시스템은 이를 해결하기 위해 역할을 명확히 분리합니다.

- **worker_1**: 주문을 브로커로 실행하는 역할
- **worker_2**: 체결/잔량을 추적하고 상태를 최종 확정하는 역할

즉, 실행과 판단을 분리해 오류 전파를 줄이고, 상태 전이를 단일 책임으로 관리합니다. ✅

---

## 🏗️ 핵심 구조 개요

### 전체 구조

![architecture](README_IMG/sequence_diagram.png)

> **[Client/API]**  
> ↓  
> **[DB 주문 생성]**  
> ↓  
> **[worker_1 - 주문 실행]**  
> ↓  
> **[Broker API]**  
> ↓  
> **[worker_2 - 상태 추적]**  
> ↓  
> **[DB 상태 업데이트]**

### 주문 상태 추적 다이어그램

![architecture_상태](README_IMG/Polling_and_Retry_다이어그램.png)  
**aggressive polling + adaptive backoff + low-frequency polling 기반 주문 상태 추적**

---

## ⚙️ Worker 역할 상세

### 부모-자식 주문 관계 다이어그램

![architecture_상태](README_IMG/Parent_Child_관계_다이어그램.png)  
**부모 - 자식 주문 관계 다이어그램 예시**

### 자식 주문 포함 시퀀스

![architecture_상태](README_IMG/자식_주문_포함_시퀀스.png)  
**자식 주문 포함 시퀀스 다이어그램**

---

### 🟦 worker_1 (주문 실행 워커)

#### 역할

- DB에서 처리 대상 주문 조회
- Broker API 호출 (매수 / 매도 / 취소 / 정정)
- 호출 성공 시 주문 상태를 `ACCEPTED` 로 갱신
- worker_2에 추적 작업 위임

#### 설계 의도

- 비즈니스 상태 판단 로직을 넣지 않음
- 상태 전이 결정을 하지 않음
- 부모/자식 주문 구분 없이 실행 관점으로 동일 처리

#### 한 줄 요약

> **"worker_1은 실행만 책임진다."**

---

### 🟥 worker_2 (주문 상태 추적 워커)

#### 역할

- Broker 체결 조회 API 폴링
- 체결/잔량/누적값을 바탕으로 주문 상태 전이
- 미완료 상태라면 재추적 스케줄링
- 자식 주문 결과를 부모 주문 정합성에 반영

#### 처리 범위

| 주문 타입 | 처리 내용 |
|---|---|
| BUY / SELL | 체결 상태 및 누적 체결량 반영 |
| CANCEL / MODIFY | 자식 주문 상태 확정 + 부모 주문 영향 반영 |

#### 한 줄 요약

> **"worker_2는 상태 머신이자 정합성 관리자다."**

---

## 🔥 핵심 도메인 개념

### 1) 부모 / 자식 주문

| 구분 | 설명 |
|---|---|
| 부모 주문 | 최초 매수/매도(NEW) 주문 |
| 자식 주문 | 정정(MODIFY), 취소(CANCEL) 주문 |

- 부모 주문은 시장 체결의 기준이 되는 원주문입니다.
- 자식 주문은 부모 주문의 수량/가격/잔량에 영향을 줍니다.

---

### 2) `delta_qty` (중요)

브로커 응답은 보통 **누적 체결 수량(cumulative filled qty)** 을 반환합니다.  
따라서 상태 반영은 누적값 그 자체가 아니라 **증분(delta)** 기준이어야 합니다.

예시:

- 이전 누적 체결: `2`
- 현재 누적 체결: `5`
- 이번 반영 수량: `delta = 3`

✅ 반드시 `delta_qty` 로만 반영해야 중복 집계를 방지할 수 있습니다.

---

### 3) 상태 판정 정책

#### 📌 부모 주문 상태

| 상태 | 의미 |
|---|---|
| ACCEPTED | 주문 접수 완료 (최종 체결/취소 미확정) |
| PARTIAL_FILLED | 일부 체결 |
| FILLED | 전량 체결 |
| CANCELED | 잔량 전체 취소 |
| FAILED | 주문 실행/처리 실패 |

부모 주문은 다음 기준으로 판단합니다.

- `remaining_qty == 0` 이고 체결 있음 → `FILLED`
- `remaining_qty > 0` 이고 체결 있음 → `PARTIAL_FILLED`
- `remaining_qty == 0` 이고 체결 없음 → `CANCELED`
- 오류 발생 → `FAILED`

#### 📌 자식 주문 상태

##### 정정 주문 (`MODIFY`)

| 상태 | 의미 |
|---|---|
| FILLED | 정정 요청 수량 반영 완료 |
| PARTIAL_FILLED | 일부만 반영 |
| FAILED | 정정 실패 |

정정은 부분 반영이 가능하므로 `PARTIAL_FILLED` 를 사용할 수 있습니다.

##### 취소 주문 (`CANCEL`)

| 상태 | 의미 |
|---|---|
| FILLED | 취소 요청 수량 전부 취소 완료 |
| FAILED | 취소 실패 |

취소 주문은 체결 이벤트가 아니라 **요청 처리 이벤트** 성격이므로 일반적으로 `PARTIAL_FILLED` 를 사용하지 않습니다.

---

### 4) 부모/자식 관계 처리 규칙

#### 원칙

- 부모 주문의 최종 상태는 항상 **부모 기준 데이터**로만 판단
- 자식 주문은 부모 상태를 직접 "결정"하지 않음
- 자식 주문은 다음 영향만 제공
  - `remaining_qty` 감소/변경
  - `delta_qty` 반영 트리거
  - 부모 상태 판정 조건 변화

#### 자식 → 부모 영향

| 자식 유형 | 부모 영향 |
|---|---|
| MODIFY | `remaining_qty` 유지 또는 감소, 조건 변화 |
| CANCEL | `remaining_qty` 감소 |

공통 규칙:

- 부모 주문의 체결 반영은 항상 `delta_qty` 기준
- 자식 주문 처리 후에도 부모 최종 판정 규칙은 동일

---

### 5) 최종 상태 판정 흐름

1. 새 브로커 응답 수신
2. 이전 누적값과 비교하여 `delta_qty` 계산
3. `filled_qty`, `remaining_qty` 갱신
4. 부모/자식 주문 타입별 상태 규칙 적용
5. 최종 상태 저장 및 필요 시 재추적 예약

---

## 🧪 실행 환경 구축

```bash
poetry init
poetry lock
poetry install
```

---

## 🔐 환경 변수

```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your_password
DB_URL=postgresql+asyncpg://postgres:your_password@localhost:5432/postgres

# Redis / Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

---

## 🚀 실행 가이드

### 1) 로컬 API 실행

```bash
poetry run uvicorn app.main:app --reload
```

### 2) Celery Worker 실행

```bash
# 큐 비우기
poetry run celery -A app.worker.celery_app.celery_app purge

# Windows
poetry run celery -A app.broker.celery_app.celery_app worker --loglevel=info --pool=solo

# Linux
poetry run celery -A app.broker.celery_app.celery_app worker --loglevel=info
```

### 3) Docker 실행

```bash
docker compose up --build

# 백그라운드 실행
docker compose up -d --build

# 개발/테스트용 컴포즈
docker compose -f docker-compose.dev.yml up --build
```

### 4) 로그 확인

```bash
docker compose logs -f

docker compose logs -f api
docker compose logs -f worker_1
docker compose logs -f worker_2
```

### 5) API 문서 접속

```text
http://localhost:8000/docs
```

---

## ✅ 테스트

### 로컬 테스트

```bash
poetry run pytest -v
```

### Docker 테스트

```bash
docker compose build test_runner
docker compose run --rm test_runner
```

---

## 🧷 운영 시 주의사항

- Docker 내부에서는 `localhost` 대신 서비스명을 사용하세요.
  - Redis: `redis:6379`
  - 외부 DB: `host.docker.internal`
- Windows에서 Celery 워커는 `--pool=solo` 옵션이 필요합니다.
- Docker 환경에서는 `--reload` 사용을 권장하지 않습니다.

---

## 📚 전략(Strategy) 모듈 문서

전략 모듈 상세 설명은 전략 폴더의 별도 문서를 참고하세요.

- 👉 [Strategy Module README](app/strategy/README.md)

> 메인 README는 공통 아키텍처/운영 중심 문서이며, 전략별 상세 내용은 위 문서에서 관리합니다.
