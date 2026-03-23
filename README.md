### 실행 환경 구축
```bash
poetry init
poetry lock
poetry install
```
---

### 환경 변수 설정
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

### 단위테스트
```bash
poetry run pytest [파일명.py] -k [실행함수명] -v
```

## 실행(로컬)
```bash
poetry run uvicorn app.main:app --reload
```

### Celery Worker 실행(로컬)
```bash
# 큐 비우기
poetry run celery -A app.worker.celery_app.celery_app purge

# windows
poetry run celery -A app.broker.celery_app.celery_app worker --loglevel=info --pool=solo

# linux
poetry run celery -A app.broker.celery_app.celery_app worker --loglevel=info
```

---

## Docker 실행 (권장)

### 1. 환경 변수
```bash
# Database (Docker 외부 DB 사용할 경우)
DB_HOST=host.docker.internal
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your_password
DB_URL=postgresql+asyncpg://postgres:your_password@host.docker.internal:5432/postgres

# Redis / Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
```

---

### 2. 실행
```bash
docker compose up --build

# 백그라운드 실행
docker compose up -d --build 
```

--- 

### 3. 로그 확인
```bash
docker compose logs -f

# 특정 서비스
docker compose logs -f api
docker compose logs -f worker_1
docker compose logs -f worker_2
```

---

### 4. 종료
```bash
docker compose down
```

---

### 5. 접속
```
http://localhost:8000/docs
```

---

### ⚠️ 주의사항
> Docker 환경에서는 localhost 대신 서비스명 사용
> Redis → redis:6379
> 외부 DB → host.docker.internal
> Windows에서 Celery는 --pool=solo 필요
> Docker 환경에서는 --reload 사용하지 않음