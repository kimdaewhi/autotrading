### 실행 환경 구축
```bash
poetry init
poetry lock
poetry install
```

### 테스트
```bash
poetry run pytest [파일명.py] -k [실행함수명] -v
```

### 실행
```bash
poetry run uvicorn app.main:app --reload
```

### Celery Worker 실행
```bash
# windows
poetry run celery -A app.broker.celery_app.celery_app worker --loglevel=info --pool=solo

# linux
poetry run celery -A app.broker.celery_app.celery_app worker --loglevel=info
```