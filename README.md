### 테스트
```bash
poetry run pytest [파일명.py] -k [실행함수명] -v
```

### 실행
```bash
poetry run uvicorn app.main:app --reload
```