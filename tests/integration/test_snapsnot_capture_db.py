"""
PortfolioSnapshotService.capture() 통합 테스트 (실 DB)

unit 테스트(test_portfolio_snapshot_service.py)는 insert_snapshot 을 패치하므로
DB 제약조건 / 타입 매핑은 검증되지 않는다. 이 테스트가 그 부분을 담당한다.

    account_service : Mock  (KIS API 호출 회피)
    db / repository : 실제  (NOT NULL, NUMERIC(18,4), unique 제약 검증)

로컬 Postgres 가 떠 있어야 한다. DB_URL 은 conftest.py 에서 localhost 로 오버라이드된다.

실행:
    pytest tests/integration/test_snapshot_capture_db.py -s
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.core.settings import settings
from app.db.models.snapshot import PortfolioSnapshot, PortfolioSnapshotHolding
from app.db.session import AsyncSessionLocal, dispose_async_engine
from app.repository.portfolio_snapshot_repository import get_snapshots_by_period
from app.services.rebalance.portfolio_snapshot_service import (
    PortfolioSnapshotService,
)
from app.strategy.runtime.position_diff import DiffAction

KST = ZoneInfo("Asia/Seoul")

# 2026-08-12 모의계좌 실측값 (삼성전자 1주 매수 직후)
#   dnca_tot_amt       10,000,000  D+0 — 매수 대금 미차감
#   prvs_rcdl_excc_amt  9,743,720  D+2 — 매수 256,250 + 수수료 30 차감
#   scts_evlu_amt         255,750
#   nass_amt            9,999,470  = D+2 + 주식
DEPOSIT_TOTAL = "10000000"
SETTLEMENT_CASH = "9743720"
STOCK_EVAL = 255_750
NET_ASSET = 9_999_470


# ─────────────────────────────────────────────────────────────
# 픽스처
#
# pytest.ini 가 asyncio_default_fixture_loop_scope=session 이라
# 기본값대로 두면 픽스처(세션 루프)와 테스트(함수 루프)가 서로 다른
# 이벤트 루프에서 돌아 asyncpg 가 'attached to a different loop' 로 터진다.
# 이 파일의 픽스처는 전부 loop_scope="function" 으로 맞춘다.
# ─────────────────────────────────────────────────────────────
@pytest_asyncio.fixture(loop_scope="function")
async def _engine_per_loop():
    """
    app.db.session 의 엔진은 전역 캐시라 최초 생성된 루프에 묶인다.
    테스트마다 폐기해 현재 함수 루프 기준으로 새로 만들어지도록 한다.
    """
    await dispose_async_engine()
    yield
    await dispose_async_engine()


@pytest_asyncio.fixture(loop_scope="function")
async def db(_engine_per_loop):
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(loop_scope="function")
async def rebalance_id(db):
    """
    테스트용 rebalances 행을 만들고, 끝나면 스냅샷까지 정리한다.

    capture() 내부에서 db.commit() 을 호출하므로 트랜잭션 롤백으로는
    정리되지 않는다. 명시적으로 DELETE 한다.
    """
    rid = uuid4()

    await db.execute(
        text(
            """
            INSERT INTO rebalances (
                id, strategy_name, universe_count, buy_signal_count,
                sell_count, buy_count, hold_count,
                total_sell_value, total_buy_value,
                dry_run, status, executed_at, completed_at
            ) VALUES (
                :rid, 'IntegrationTest', 1, 1, 0, 1, 0, 0, 256250,
                false, 'COMPLETED', now(), now()
            )
            """
        ),
        {"rid": rid},
    )
    await db.commit()

    yield rid

    # 정리: holdings → snapshots → rebalances 순
    await db.rollback()

    snapshot_ids = (
        (
            await db.execute(
                select(PortfolioSnapshot.id).where(
                    PortfolioSnapshot.rebalance_id == str(rid)
                )
            )
        )
        .scalars()
        .all()
    )
    if snapshot_ids:
        await db.execute(
            delete(PortfolioSnapshotHolding).where(
                PortfolioSnapshotHolding.snapshot_id.in_(snapshot_ids)
            )
        )
        await db.execute(
            delete(PortfolioSnapshot).where(PortfolioSnapshot.id.in_(snapshot_ids))
        )
    await db.execute(text("DELETE FROM rebalances WHERE id = :rid"), {"rid": rid})
    await db.commit()


# ─────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────
def _holding(code, name, qty, avg_price, current_price="0"):
    """HoldingRead 형태의 더미 보유 종목 (KIS 응답처럼 전부 문자열)"""
    return SimpleNamespace(
        stock_code=code,
        stock_name=name,
        holding_qty=qty,
        avg_buy_price=avg_price,
        current_price=current_price,
    )


def _account_service(holdings):
    """KIS 호출만 Mock. DB 는 실제를 쓴다."""
    svc = AsyncMock()
    svc.get_holding_list.return_value = holdings
    svc.get_account_summary.return_value = SimpleNamespace(
        deposit_total_amount=DEPOSIT_TOTAL,
        settlement_cash_amount=SETTLEMENT_CASH,
    )
    return svc


async def _capture(db, rebalance_id, holdings):
    service = PortfolioSnapshotService(_account_service(holdings))
    return await service.capture(
        db=db,
        rebalance_id=str(rebalance_id),
        snapshot_type=DiffAction.REBALANCE,
    )


async def _fetch(db, snapshot_id):
    snapshot = (
        await db.execute(
            select(PortfolioSnapshot).where(PortfolioSnapshot.id == snapshot_id)
        )
    ).scalar_one()

    holdings = (
        (
            await db.execute(
                select(PortfolioSnapshotHolding)
                .where(PortfolioSnapshotHolding.snapshot_id == snapshot_id)
                .order_by(PortfolioSnapshotHolding.stock_code)
            )
        )
        .scalars()
        .all()
    )
    return snapshot, holdings


def _samsung():
    """삼성전자 1주 (실측 기준). 테스트마다 새 객체를 만들어 공유 상태를 피한다."""
    return [_holding("005930", "삼성전자", "1", "256250.0000", "255750")]


# ─────────────────────────────────────────────────────────────
# 1. 실제 저장 — 스키마 제약 통과
# ─────────────────────────────────────────────────────────────
async def test_capture_persists_to_db(db, rebalance_id):
    """
    NOT NULL / 타입 매핑이 실제 스키마를 통과하는지.
    account_no, account_product_code 가 NOT NULL 이므로
    누락되면 여기서 IntegrityError 로 터진다.
    """
    snapshot_id = await _capture(db, rebalance_id, _samsung())
    snapshot, saved = await _fetch(db, snapshot_id)

    assert snapshot.account_no == settings.KIS_ACCOUNT_NO
    assert snapshot.account_product_code == settings.KIS_ACCOUNT_PRODUCT_CODE
    assert snapshot.snapshot_type == DiffAction.REBALANCE.value
    assert len(saved) == 1

    print(
        f"\n저장 확인  account={snapshot.account_no}-{snapshot.account_product_code} "
        f"cash={snapshot.cash_amount:,} trading_date={snapshot.trading_date}"
    )


# ─────────────────────────────────────────────────────────────
# 2. cash_amount 는 D+2
# ─────────────────────────────────────────────────────────────
async def test_cash_amount_is_settlement_not_deposit(db, rebalance_id):
    """
    D+0 예수금을 쓰면 매수 대금이 아직 차감되지 않아,
    주식 평가액과 더할 때 같은 돈을 두 번 세게 된다.

        D+2 + 주식 =  9,743,720 + 255,750 =  9,999,470  (= 순자산)
        D+0 + 주식 = 10,000,000 + 255,750 = 10,255,750  (+256,280 과대)
    """
    snapshot_id = await _capture(db, rebalance_id, _samsung())
    snapshot, _ = await _fetch(db, snapshot_id)

    assert snapshot.cash_amount == int(SETTLEMENT_CASH)
    assert snapshot.cash_amount != int(DEPOSIT_TOTAL)

    # NAV 등식 재현
    assert snapshot.cash_amount + STOCK_EVAL == NET_ASSET

    print(f"\nNAV 등식  {snapshot.cash_amount:,} + {STOCK_EVAL:,} = {NET_ASSET:,}")


# ─────────────────────────────────────────────────────────────
# 3. trading_date — 없으면 지표 조회가 0건
# ─────────────────────────────────────────────────────────────
async def test_trading_date_enables_period_query(db, rebalance_id):
    """
    get_snapshots_by_period 는 trading_date 로 필터링한다.
    NULL 이면 조회가 0건이 되어 지표 산출 자체가 불가능하다.
    """
    snapshot_id = await _capture(db, rebalance_id, _samsung())
    snapshot, _ = await _fetch(db, snapshot_id)

    assert snapshot.trading_date is not None
    assert snapshot.trading_date == snapshot.snapshot_at.astimezone(KST).date()

    # 실제 지표 파이프라인이 쓰는 조회로 잡히는지
    found = await get_snapshots_by_period(
        db=db,
        account_no=settings.KIS_ACCOUNT_NO,
        account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
        start_date=snapshot.trading_date,
        end_date=snapshot.trading_date,
    )
    assert any(s.id == snapshot_id for s in found)

    print(f"\ntrading_date={snapshot.trading_date} — 기간 조회로 {len(found)}건 확인")


# ─────────────────────────────────────────────────────────────
# 4. Decimal 정밀도 — DB 왕복 후에도 유지
# ─────────────────────────────────────────────────────────────
async def test_decimal_precision_survives_db_roundtrip(db, rebalance_id):
    """NUMERIC(18,4) 이므로 소수점 4자리까지 보존되어야 한다."""
    holdings = [_holding("112610", "씨에스윈드", "6", "62108.3333", "63000")]

    snapshot_id = await _capture(db, rebalance_id, holdings)
    _, saved = await _fetch(db, snapshot_id)

    h = saved[0]
    assert isinstance(h.avg_buy_price, Decimal)
    assert h.avg_buy_price == Decimal("62108.3333")
    assert h.holding_qty == 6

    print(f"\n평단가 왕복  {h.avg_buy_price}")


# ─────────────────────────────────────────────────────────────
# 5. unique(snapshot_id, stock_code) — NAV 2배 방지
# ─────────────────────────────────────────────────────────────
async def test_duplicate_stock_code_rejected(db, rebalance_id):
    """
    같은 스냅샷에 같은 종목이 두 번 들어가면 NAV 가 조용히 2배가 된다.
    DB unique 제약이 이를 막는지 확인한다.
    """
    snapshot_id = await _capture(db, rebalance_id, _samsung())

    db.add(
        PortfolioSnapshotHolding(
            id=uuid4(),
            snapshot_id=snapshot_id,
            stock_code="005930",  # 중복
            stock_name="삼성전자",
            holding_qty=1,
            avg_buy_price=Decimal("256250.0000"),
            current_price=Decimal("255750"),
        )
    )

    with pytest.raises(IntegrityError):
        await db.commit()

    await db.rollback()
    print("\nunique(snapshot_id, stock_code) 제약 동작 확인")


# ─────────────────────────────────────────────────────────────
# 6. 멱등성 — 실 DB 기준
# ─────────────────────────────────────────────────────────────
async def test_idempotent_on_db(db, rebalance_id):
    """두 번 호출해도 스냅샷은 1건이어야 한다."""
    first = await _capture(db, rebalance_id, _samsung())
    second = await _capture(db, rebalance_id, _samsung())

    assert str(first) == str(second)

    rows = (
        (
            await db.execute(
                select(PortfolioSnapshot).where(
                    PortfolioSnapshot.rebalance_id == str(rebalance_id)
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1

    print(f"\n멱등 확인  snapshot 1건 유지 ({first})")


# ─────────────────────────────────────────────────────────────
# 7. 파싱 실패 종목이 있어도 스냅샷은 저장된다
# ─────────────────────────────────────────────────────────────
async def test_unparsable_price_does_not_break_snapshot(db, rebalance_id):
    """
    거래정지 종목은 prpr 이 빈 문자열로 오는 경우가 있다.
    종목 하나 때문에 그날 스냅샷 전체가 날아가면 안 된다.
    """
    holdings = [
        _holding("005930", "삼성전자", "1", "256250.0000", "255750"),
        _holding("900110", "거래정지종목", "10", "5000.0000", ""),
    ]

    snapshot_id = await _capture(db, rebalance_id, holdings)
    _, saved = await _fetch(db, snapshot_id)

    assert len(saved) == 2

    by_code = {h.stock_code: h for h in saved}
    assert by_code["005930"].current_price == Decimal("255750")
    assert by_code["900110"].current_price is None
    assert by_code["900110"].holding_qty == 10  # 수량은 살아야 NAV 계산 가능

    print("\n파싱 실패 종목 포함 저장 확인 — current_price=None")