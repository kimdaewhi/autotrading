"""
PortfolioSnapshotService.capture() 단위 테스트

실제 KIS API / DB 없이 capture 로직만 검증한다.
시나리오:
    1. 정상 캡처 (holdings → 스냅샷 저장)
    2. 멱등성 (기존 스냅샷 존재 → 조기 return, 외부 호출 없음)
    3. 타입 변환 (문자열 → int / Decimal, 소수점 평균단가 정밀도)
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.strategy.runtime.position_diff import DiffAction
from app.services.rebalance.portfolio_snapshot_service import (
    PortfolioSnapshotService,
)


def _make_holding(code: str, name: str, qty: str, avg_price: str):
    """HoldingRead 형태의 더미 보유 종목 (KIS 응답처럼 전부 문자열)"""
    return SimpleNamespace(
        stock_code=code,
        stock_name=name,
        holding_qty=qty,
        avg_buy_price=avg_price,
    )


def _make_account_service(holdings: list, cash: str) -> AsyncMock:
    """account_service mock — get_holding_list / get_account_summary"""
    svc = AsyncMock()
    svc.get_holding_list.return_value = holdings
    svc.get_account_summary.return_value = SimpleNamespace(cash_amount=cash)
    return svc


@pytest.mark.asyncio
async def test_scenario_1_normal_capture():
    """시나리오 1: holdings 2건 → 스냅샷 메타 1 + holdings 2 저장"""
    holdings = [
        _make_holding("005930", "삼성전자", "10", "70000.0000"),
        _make_holding("000660", "SK하이닉스", "5", "150000.0000"),
    ]
    account_service = _make_account_service(holdings, cash="3256024")
    service = PortfolioSnapshotService(account_service)

    with patch(
        "app.services.rebalance.portfolio_snapshot_service.get_snapshot_id_by_rebalance",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.rebalance.portfolio_snapshot_service.insert_snapshot",
        new=AsyncMock(),
    ) as mock_insert:
        snapshot_id = await service.capture(
            db=AsyncMock(),
            rebalance_id="reb-001",
            snapshot_type=DiffAction.REBALANCE,
        )

    # insert_snapshot이 메타 1 + holdings 2건으로 호출됐는지
    assert mock_insert.await_count == 1
    _, snapshot_arg, holdings_arg = mock_insert.await_args.args
    assert snapshot_arg.rebalance_id == "reb-001"
    assert snapshot_arg.snapshot_type == DiffAction.REBALANCE.value
    assert snapshot_arg.cash_amount == 3256024  # 문자열 → int
    assert len(holdings_arg) == 2
    assert snapshot_id == snapshot_arg.id  # 반환값 = 생성된 id

    print("✅ 시나리오 1 통과: 정상 캡처")


@pytest.mark.asyncio
async def test_scenario_2_idempotent():
    """시나리오 2: 기존 스냅샷 존재 → KIS 조회/insert 없이 기존 id 반환"""
    account_service = _make_account_service([], cash="0")
    service = PortfolioSnapshotService(account_service)

    with patch(
        "app.services.rebalance.portfolio_snapshot_service.get_snapshot_id_by_rebalance",
        new=AsyncMock(return_value="existing-snap-id"),
    ), patch(
        "app.services.rebalance.portfolio_snapshot_service.insert_snapshot",
        new=AsyncMock(),
    ) as mock_insert:
        snapshot_id = await service.capture(
            db=AsyncMock(),
            rebalance_id="reb-001",
            snapshot_type=DiffAction.REBALANCE,
        )

    assert snapshot_id == "existing-snap-id"
    mock_insert.assert_not_awaited()                      # 저장 안 함
    account_service.get_holding_list.assert_not_awaited()  # KIS 조회도 안 함

    print("✅ 시나리오 2 통과: 멱등성 — 조기 return")


@pytest.mark.asyncio
async def test_scenario_3_type_conversion():
    """시나리오 3: 문자열 → int/Decimal 변환, 소수점 평균단가 정밀도 유지"""
    holdings = [
        _make_holding("112610", "씨에스윈드", "6", "62108.3333"),
    ]
    account_service = _make_account_service(holdings, cash="1752140")
    service = PortfolioSnapshotService(account_service)

    with patch(
        "app.services.rebalance.portfolio_snapshot_service.get_snapshot_id_by_rebalance",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.rebalance.portfolio_snapshot_service.insert_snapshot",
        new=AsyncMock(),
    ) as mock_insert:
        await service.capture(
            db=AsyncMock(),
            rebalance_id="reb-002",
            snapshot_type=DiffAction.REBALANCE,
        )

    _, _, holdings_arg = mock_insert.await_args.args
    h = holdings_arg[0]
    assert h.holding_qty == 6 and isinstance(h.holding_qty, int)
    assert h.avg_buy_price == Decimal("62108.3333")  # float 거치면 깨짐
    assert isinstance(h.avg_buy_price, Decimal)

    print("✅ 시나리오 3 통과: 타입 변환 + 소수점 정밀도")