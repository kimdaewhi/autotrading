"""
디스코드 웹훅 알림 테스트 스크립트

사용법:
    python -m tests.test_discord_webhook

    또는 개별 테스트:
    python -m tests.test_discord_webhook --case success
    python -m tests.test_discord_webhook --case warning
    python -m tests.test_discord_webhook --case fail
    python -m tests.test_discord_webhook --case dry_run
    python -m tests.test_discord_webhook --case order_error
    python -m tests.test_discord_webhook --case health
"""

import sys
import asyncio
import argparse
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# ── Mock 클래스 (실제 import 없이 테스트 가능하도록) ──

class DiffAction(Enum):
    SELL = "SELL"
    BUY = "BUY"
    HOLD = "HOLD"


@dataclass
class PositionDiffItem:
    stock_code: str = ""
    stock_name: str = ""
    action: DiffAction = DiffAction.HOLD
    current_qty: int = 0
    current_price: int = 0
    current_value: int = 0
    target_qty: int = 0
    target_value: int = 0
    order_qty: int = 0
    order_value: int = 0
    momentum_return: float = 0.0
    momentum_rank: int = 0


@dataclass
class PositionDiffResult:
    sell_list: list = field(default_factory=list)
    buy_list: list = field(default_factory=list)
    hold_list: list = field(default_factory=list)
    total_sell_value: int = 0
    total_buy_value: int = 0
    available_cash: int = 0
    estimated_cash_after: int = 0
    target_count: int = 0
    current_count: int = 0


@dataclass
class FillResult:
    total_orders: int = 0
    filled_orders: int = 0
    canceled_orders: int = 0
    failed_orders: int = 0
    total_filled_amount: int = 0
    timed_out: bool = False
    canceled_by_timeout: int = 0


@dataclass
class OrderGenerationResult:
    rebalance_id: str = ""
    sell_orders: list = field(default_factory=list)
    buy_orders: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    sell_fill_result: FillResult | None = None
    buy_fill_result: FillResult | None = None

    @property
    def total_orders(self) -> int:
        return len(self.sell_orders) + len(self.buy_orders)


@dataclass
class RebalanceResult:
    rebalance_id: str = ""
    executed_at: str = ""
    universe_count: int = 0
    signal_buy_count: int = 0
    diff_result: PositionDiffResult | None = None
    order_result: OrderGenerationResult | None = None
    dry_run: bool = True
    success: bool = False
    error_message: str = ""


# ── Mock 데이터 생성 ──

def _make_diff_result() -> PositionDiffResult:
    return PositionDiffResult(
        sell_list=[
            PositionDiffItem(
                stock_code="001820", stock_name="삼화콘덴서",
                action=DiffAction.SELL,
                current_qty=13, current_price=62600,
                current_value=813800, order_qty=13, order_value=813800,
            ),
            PositionDiffItem(
                stock_code="083450", stock_name="GST",
                action=DiffAction.SELL,
                current_qty=23, current_price=36000,
                current_value=828000, order_qty=23, order_value=828000,
            ),
        ],
        buy_list=[
            PositionDiffItem(
                stock_code="252990", stock_name="샘씨엔에스",
                action=DiffAction.BUY,
                current_price=10190, target_value=1610020,
                order_qty=158, order_value=1610020,
                momentum_return=0.435, momentum_rank=6,
            ),
            PositionDiffItem(
                stock_code="001060", stock_name="JW중외제약",
                action=DiffAction.BUY,
                current_price=31300, target_value=1596300,
                order_qty=51, order_value=1596300,
                momentum_return=0.429, momentum_rank=7,
            ),
            PositionDiffItem(
                stock_code="033240", stock_name="자화전자",
                action=DiffAction.BUY,
                current_price=33000, target_value=1584000,
                order_qty=48, order_value=1584000,
                momentum_return=0.425, momentum_rank=8,
            ),
        ],
        hold_list=[
            PositionDiffItem(
                stock_code="003000", stock_name="부광약품",
                action=DiffAction.HOLD,
                current_qty=113, current_value=862190,
            ),
            PositionDiffItem(
                stock_code="005090", stock_name="SGC에너지",
                action=DiffAction.HOLD,
                current_qty=16, current_value=868800,
            ),
            PositionDiffItem(
                stock_code="005880", stock_name="대한해운",
                action=DiffAction.HOLD,
                current_qty=295, current_value=861400,
            ),
        ],
        total_sell_value=1641800,
        total_buy_value=4790320,
        available_cash=8691195,
        estimated_cash_after=4092575,
        target_count=10,
        current_count=9,
    )


def _make_order_result_success() -> OrderGenerationResult:
    return OrderGenerationResult(
        rebalance_id="5f58bd5a-d3ed-48a5-81dd-aaabe9ec8d41",
        sell_orders=[{}, {}],  # 길이만 필요
        buy_orders=[{}, {}, {}],
        sell_fill_result=FillResult(
            total_orders=2, filled_orders=2,
            total_filled_amount=1641800,
        ),
        buy_fill_result=FillResult(
            total_orders=3, filled_orders=3,
        ),
    )


def _make_order_result_timeout() -> OrderGenerationResult:
    return OrderGenerationResult(
        rebalance_id="5f58bd5a-d3ed-48a5-81dd-aaabe9ec8d41",
        sell_orders=[{}, {}],
        buy_orders=[{}, {}, {}],
        sell_fill_result=FillResult(
            total_orders=2, filled_orders=2,
            total_filled_amount=1641800,
        ),
        buy_fill_result=FillResult(
            total_orders=3, filled_orders=2,
            timed_out=True, canceled_by_timeout=1,
        ),
    )


# ── 테스트 케이스 ──

async def test_success_card():
    """✅ 리밸런싱 성공 카드"""
    from app.utils.discord import send_rebalance_alert

    result = RebalanceResult(
        rebalance_id="5f58bd5a-d3ed-48a5-81dd-aaabe9ec8d41",
        executed_at=datetime.now().isoformat(),
        universe_count=45,
        signal_buy_count=10,
        diff_result=_make_diff_result(),
        order_result=_make_order_result_success(),
        dry_run=False,
        success=True,
    )

    ok = await send_rebalance_alert(result)
    print(f"[성공 카드] 전송 {'✅' if ok else '❌'}")
    return ok


async def test_warning_card():
    """⚠️ 타임아웃 경고 카드"""
    from app.utils.discord import send_rebalance_alert

    result = RebalanceResult(
        rebalance_id="5f58bd5a-d3ed-48a5-81dd-aaabe9ec8d41",
        executed_at=datetime.now().isoformat(),
        universe_count=45,
        signal_buy_count=10,
        diff_result=_make_diff_result(),
        order_result=_make_order_result_timeout(),
        dry_run=False,
        success=True,
    )

    ok = await send_rebalance_alert(result)
    print(f"[경고 카드] 전송 {'✅' if ok else '❌'}")
    return ok


async def test_fail_card():
    """❌ 리밸런싱 실패 카드"""
    from app.utils.discord import send_rebalance_alert

    result = RebalanceResult(
        rebalance_id="5f58bd5a-d3ed-48a5-81dd-aaabe9ec8d41",
        executed_at=datetime.now().isoformat(),
        universe_count=0,
        signal_buy_count=0,
        dry_run=False,
        success=False,
        error_message="F-Score 스크리닝 결과 종목이 없습니다.",
    )

    ok = await send_rebalance_alert(result)
    print(f"[실패 카드] 전송 {'✅' if ok else '❌'}")
    return ok


async def test_dry_run_card():
    """🔍 DRY RUN 카드"""
    from app.utils.discord import send_rebalance_alert

    result = RebalanceResult(
        rebalance_id="5f58bd5a-d3ed-48a5-81dd-aaabe9ec8d41",
        executed_at=datetime.now().isoformat(),
        universe_count=45,
        signal_buy_count=10,
        diff_result=_make_diff_result(),
        dry_run=True,
        success=True,
    )

    ok = await send_rebalance_alert(result)
    print(f"[DRY RUN 카드] 전송 {'✅' if ok else '❌'}")
    return ok


async def test_order_error_card():
    """🚨 주문 에러 카드"""
    from app.utils.discord import send_order_error_alert

    ok = await send_order_error_alert(
        stock_code="017900",
        stock_name="광전자",
        order_id="6d854bc4-c3e2-4e2c-8b42-a1d079752768",
        order_action="BUY",
        error_message="KIS API timeout: 주문 체결 조회 시간 초과",
        context={
            "rebalance_id": "ef35f5d7",
            "order_qty": "63주",
            "order_type": "시장가",
        },
    )
    print(f"[주문 에러 카드] 전송 {'✅' if ok else '❌'}")
    return ok


async def test_health_card():
    """🏥 헬스체크 카드"""
    from app.utils.discord import send_health_alert

    # 정상
    ok1 = await send_health_alert(
        title="시스템 헬스체크",
        message="워커: ✅ alive\nRedis: ✅ connected\nKIS 토큰: ✅ valid (만료까지 3시간)",
        is_healthy=True,
    )
    print(f"[헬스 정상 카드] 전송 {'✅' if ok1 else '❌'}")

    # 비정상
    ok2 = await send_health_alert(
        title="시스템 헬스체크",
        message="워커: ✅ alive\nRedis: ❌ connection refused\nKIS 토큰: ⚠️ 만료됨",
        is_healthy=False,
    )
    print(f"[헬스 에러 카드] 전송 {'✅' if ok2 else '❌'}")

    return ok1 and ok2


# ── 실행 ──

CASES = {
    "success": test_success_card,
    "warning": test_warning_card,
    "fail": test_fail_card,
    "dry_run": test_dry_run_card,
    "order_error": test_order_error_card,
    "health": test_health_card,
}


async def run_all():
    print("=" * 50)
    print("디스코드 웹훅 알림 테스트")
    print("=" * 50)

    results = {}
    for name, func in CASES.items():
        results[name] = await func()
        await asyncio.sleep(1)  # rate limit 방지

    print("\n" + "=" * 50)
    print("결과 요약")
    print("=" * 50)
    for name, ok in results.items():
        print(f"  {name}: {'✅' if ok else '❌'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="디스코드 웹훅 테스트")
    parser.add_argument(
        "--case",
        choices=list(CASES.keys()),
        help="개별 테스트 케이스 (미지정 시 전체 실행)",
    )
    args = parser.parse_args()

    if args.case:
        asyncio.run(CASES[args.case]())
    else:
        asyncio.run(run_all())