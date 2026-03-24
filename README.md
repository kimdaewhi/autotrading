# 📌 Auto Trading System

## 핵심 구조 개요

### Worker 역할

#### worker_1 (주문 실행 워커)
- DB에 저장된 주문을 읽어서 실제 주문 API 호출
- 주문 성공 시 상태를 `ACCEPTED`로 변경
- 체결 추적을 위해 worker_2 호출

#### worker_2 (주문 상태 추적 워커)
- 주문번호 기반으로 체결 조회 API 호출
- 체결 상태에 따라 `PARTIAL_FILLED / FILLED` 업데이트
- 미체결 상태면 재추적 수행 (delay 기반)

---

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