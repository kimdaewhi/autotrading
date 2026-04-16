"""
DART 재무제표 조회 불가 종목 블랙리스트

⭐ 역할
    - F-Score 스크리닝 전 단계에서 유니버스에서 아예 제외할 종목 목록
    - DART API가 공식적/구조적으로 재무제표를 제공하지 않는 종목들

⭐ 블랙리스트 사유
    1. 금융업 — DART fnlttSinglAcntAll API가 공식 제외 (삼성증권, 금융지주 등)
    2. 특수법인 — 리츠, 인프라펀드, SPAC 등 재무제표 구조가 일반 기업과 상이
    3. 수동 등록 — 기타 사유로 제외가 필요한 종목

⚠️ 네거티브 캐시(dart_unavailable 테이블)와의 차이
    - 블랙리스트: 영구적 판단, 코드 상수로 관리, 유니버스 단계에서 제외
    - 네거티브 캐시: 조회 결과 기반 학습, DB 저장, 런타임에 축적

# TODO: 금융업 종목 파악되는 대로 FINANCIAL_STOCK_CODES에 추가
"""


# ── 금융업 (DART API 공식 제외 대상) ──
FINANCIAL_STOCK_CODES: set[str] = set()


# ── 특수법인 (리츠, 인프라펀드, SPAC 등) ──
SPECIAL_ENTITY_CODES: set[str] = {
    "088980",  # 맥쿼리인프라 (투융자회사)
}


# ── 수동 등록 (기타 사유) ──
MANUAL_BLACKLIST: set[str] = set()


# ── 통합 블랙리스트 ──
DART_UNAVAILABLE_CODES: set[str] = (
    FINANCIAL_STOCK_CODES | SPECIAL_ENTITY_CODES | MANUAL_BLACKLIST
)