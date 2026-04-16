from datetime import datetime, timezone
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.dart_financial_statement import DartFinancialStatement
from app.db.models.dart_unavailable import DartUnavailable


# ⚙️ DB에 이미 적재된 종목코드 집합 조회
async def find_existing_stock_codes(
    db: AsyncSession,
    stock_codes: list[str],
    bsns_year: str,
    reprt_code: str,
) -> set[str]:
    """
    DB에 이미 적재된 종목코드 집합 반환
    """
    query = (
        select(DartFinancialStatement.stock_code)
        .where(
            DartFinancialStatement.stock_code.in_(stock_codes),
            DartFinancialStatement.bsns_year == bsns_year,
            DartFinancialStatement.reprt_code == reprt_code,
        )
        .distinct()
    )

    result = await db.execute(query)
    return {row[0] for row in result.all()}


# ⚙️ 여러 종목의 재무제표 일괄 조회
async def find_by_stock_codes(
    db: AsyncSession,
    stock_codes: list[str],
    bsns_year: str,
    reprt_code: str,
) -> list:
    """
    여러 종목의 재무제표 일괄 조회
    """
    query = (
        select(DartFinancialStatement)
        .where(
            DartFinancialStatement.stock_code.in_(stock_codes),
            DartFinancialStatement.bsns_year == bsns_year,
            DartFinancialStatement.reprt_code == reprt_code,
        )
    )

    result = await db.execute(query)
    return result.scalars().all()


# ⚙️ DART 재무제표 DataFrame 벌크 INSERT
async def bulk_insert_financial_statements(
    db: AsyncSession,
    df: pd.DataFrame,
) -> None:
    """
    DART 재무제표 DataFrame을 벌크 INSERT
    """
    db_columns = [c.key for c in DartFinancialStatement.__table__.columns]
    df = df[[c for c in db_columns if c in df.columns]].copy()

    # 금액 컬럼 숫자 변환 확보
    bigint_cols = ["thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount", "thstrm_add_amount"]
    for col in bigint_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # PK 기준 중복 제거
    df = df.drop_duplicates(subset=["rcept_no", "sj_div", "account_id"], keep="last")

    # NaN → None (to_dict 시 float('nan') → SQLAlchemy NULL)
    records = []
    for row in df.to_dict(orient="records"):
        cleaned = {
            k: (None if isinstance(v, float) and pd.isna(v) else v)
            for k, v in row.items()
        }
        records.append(DartFinancialStatement(**cleaned))

    db.add_all(records)
    await db.flush()


# ⚙️ 조회 불가로 캐시된 종목코드 집합 조회
async def find_unavailable_codes(
    db: AsyncSession,
    stock_codes: list[str],
    bsns_year: str,
    reprt_code: str,
) -> set[str]:
    """
    주어진 종목 리스트 중 조회 불가로 캐시된 종목코드 set 반환
    
    Parameters
    ----------
    stock_codes : 검사할 종목코드 리스트
    bsns_year : 사업연도 (ex. "2024")
    reprt_code : 보고서코드 (ex. "11011")
    
    Returns
    -------
    set[str] : 캐시된 (조회 불가) 종목코드 set
    """
    if not stock_codes:
        return set()
    
    stmt = select(DartUnavailable.stock_code).where(
        DartUnavailable.stock_code.in_(stock_codes),
        DartUnavailable.bsns_year == bsns_year,
        DartUnavailable.reprt_code == reprt_code,
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.all()}



# ⚙️ 복수 종목을 한번에 조회 불가로 기록 (bulk upsert)
async def mark_unavailable_bulk(
    db: AsyncSession,
    records: list[dict],
) -> None:
    """
    복수 종목을 한번에 조회 불가로 기록 (bulk upsert)
    
    Parameters
    ----------
    records : [{"stock_code": "005930", "bsns_year": "2024", "reprt_code": "11011", "reason": "no_data"}, ...]
    """
    if not records:
        return
    
    now = datetime.now(timezone.utc)
    values = [
        {
            "stock_code": r["stock_code"],
            "bsns_year": r["bsns_year"],
            "reprt_code": r["reprt_code"],
            "reason": r.get("reason", "no_data"),
            "checked_at": now,
        }
        for r in records
    ]
    
    stmt_insert = insert(DartUnavailable).values(values)
    stmt = stmt_insert.on_conflict_do_update(
        index_elements=["stock_code", "bsns_year", "reprt_code"],
        set_={
            "reason": stmt_insert.excluded.reason,
            "checked_at": now,
        },
    )
    await db.execute(stmt)