# 📌 Auto Trading System


## 실행 환경 구축

```bash
poetry init
poetry lock
poetry install
```

---

## 환경 변수

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

## 실행 (로컬)

```bash
poetry run uvicorn app.main:app --reload
```

---

## Celery Worker 실행

```bash
# 큐 비우기
poetry run celery -A app.worker.celery_app.celery_app purge

# Windows
poetry run celery -A app.broker.celery_app.celery_app worker --loglevel=info --pool=solo

# Linux
poetry run celery -A app.broker.celery_app.celery_app worker --loglevel=info
```

---

## Docker 실행

```bash
docker compose up --build

# 백그라운드 실행
docker compose up -d --build

# 테스트용
docker compose -f docker-compose.dev.yml up --build
```

---

## 로그 확인

```bash
docker compose logs -f

docker compose logs -f api
docker compose logs -f worker_1
docker compose logs -f worker_2
```

---

## 접속

```
http://localhost:8000/docs
```

---

## 테스트

```bash
poetry run pytest -v
```

---

## Docker 테스트 실행

```bash
docker compose build test_runner
docker compose run --rm test_runner
```

---

## ⚠️ 주의사항

- Docker 환경에서는 `localhost` 대신 서비스명 사용
- Redis → `redis:6379`
- 외부 DB → `host.docker.internal`
- Windows에서 Celery는 `--pool=solo` 필요
- Docker 환경에서는 `--reload` 사용하지 않음
---


# ⭐ 핵심 구조 개요

## 🧭 시스템 개요

본 시스템은 주문을 **비동기 워커 기반으로 처리**하여 다음 단계를 분리한다.

1. 주문 생성 (API)
2. 주문 실행 (worker_1)
3. 체결 추적 및 상태 반영 (worker_2)

핵심은 **주문 실행과 상태 처리를 완전히 분리**하는 것이다.

## 🏗️ 전체 구조
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


![architecture_상태](README_IMG/상태_다이어그램.png)
**주문 상태 변화 다이어그램**


![architecture_상태](README_IMG/Polling_and_Retry_다이어그램.png)
**aggressive polling + adaptive backoff  + low-frequency polling 을 이용한 주문 상태 추적**

---
## ⚙️ Worker 역할 상세

![architecture_상태](README_IMG/Parent_Child_관계_다이어그램.png)
**부모 - 자식 주문 관계 다이어그램 예시**

![architecture_상태](README_IMG/자식_주문_포함_시퀀스.png)
**자식 주문 포함 시퀀스 다이어그램**

### 🟦 worker_1 (주문 실행 워커)

#### 역할
- DB에서 주문 조회
- Broker API 호출 (매수 / 매도 / 취소 / 정정)
- 성공 시 상태를 `ACCEPTED`로 변경
- worker_2 호출 (체결 추적 시작)

#### 특징
- 비즈니스 로직 없음
- 상태 판단 없음
- 부모/자식 구분 없이 동일 처리

#### 정리
"실행만 담당하는 워커"

---

### 🟥 worker_2 (주문 상태 추적 워커)

#### 역할
- Broker 체결 조회 API 호출
- 체결 상태에 따라 주문 상태 업데이트
- 미체결이면 재추적 (polling)
- 자식 주문일 경우 원주문 상태까지 반영

#### 처리 범위

| 주문 타입 | 처리 내용 |
|----------|----------|
| BUY / SELL | 체결 상태 업데이트 |
| CANCEL / MODIFY | 자기 상태 + 원주문 영향 반영 |

#### 정리
"상태 머신 + 정합성 관리자"

---

## 🔥 핵심 개념


### 1. 부모 / 자식 주문

| 구분 | 설명 |
|------|------|
| 부모 주문 | 최초 매수 / 매도 |
| 자식 주문 | 취소(CANCEL), 정정(MODIFY) |

---

### 2. delta_qty (중요)

Broker는 **누적 체결 수량**을 반환한다.  
이전: 2, 현재: 5  
→ delta = 3

👉 원주문에는 delta만 반영해야 한다.

---

## 📊 시나리오 기반 설명


### ✅ 시나리오 1: 전량 취소
> **[부모 주문]**  
> 삼성전자 10주 매수  
> → 체결 없음  
> → 상태: ACCEPTED
> 
> **[자식 주문]**  
> 10주 취소 요청  
> worker_1 → 실행
> worker_2 → 취소 완료
> 
> **[결과]**  
> remaining_qty = 0  
> → 상태: CANCELED

### ✅ 시나리오 2: 부분 체결 + 혼합 처리
> **[부모 주문]**  
> 삼성전자 10주 매수  
> → 4주 체결  
> → 상태: PARTIAL_FILLED  
> → remaining: 6  
> 
> **[자식 주문 1]**  
> 5주 정정
> 
> **[자식 주문 2]**  
> 1주 취소
> 
> **worker_2 처리**
> 
> **[결과]**  
> remaining_qty = 0  
> → 상태: CANCELED

👉 핵심
- 자식 주문 처리량만큼 remaining 감소
- 누적값이 아닌 delta 기준 반영

## ⚠️ 중요 설계 포인트

### 1. worker_1은 판단하지 않는다
- 단순 실행만 수행

---

### 2. worker_2가 모든 상태를 결정한다
- 상태 전이 책임 집중

---

### 3. 중복 반영 방지
- 반드시 delta_qty 사용

---

### 4. 부모-자식 관계 유지
- 자식 주문은 원주문에 영향 줌

---