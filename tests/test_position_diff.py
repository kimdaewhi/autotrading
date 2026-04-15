"""
PositionDiffCalculator 단위 테스트

실제 API 호출 없이 diff 계산 로직만 검증한다.
시나리오:
    1. 신규 진입 (보유 없음 → BUY 시그널)
    2. 전량 청산 (보유 있음 → BUY 시그널 없음)
    3. 유지 + 신규 매수 (일부 겹침)
    4. 완전 교체 (겹침 없음)
    5. BUY 시그널 없음 (전량 청산만)
    6. 고가 종목으로 인한 0주 매수 제외
"""

import pandas as pd
from app.strategy.runtime.position_diff import (
    CurrentHolding,
    DiffAction,
    PositionDiffCalculator,
)


def _make_signal_df(returns: dict[str, float], top_n: int = 10) -> pd.DataFrame:
    """모멘텀 시그널 DataFrame 생성 헬퍼"""
    from app.core.enums import STRATEGY_SIGNAL
    
    result = pd.DataFrame({"return": pd.Series(returns)})
    result["rank"] = result["return"].rank(ascending=False)
    result["signal"] = STRATEGY_SIGNAL.HOLD
    
    buy_mask = (result["rank"] <= top_n) & (result["return"] > 0)
    result.loc[buy_mask, "signal"] = STRATEGY_SIGNAL.BUY
    result.loc[~buy_mask, "signal"] = STRATEGY_SIGNAL.SELL
    
    return result


def test_scenario_1_fresh_entry():
    """시나리오 1: 보유 종목 없이 신규 진입"""
    calc = PositionDiffCalculator(cash_buffer_ratio=0.0)  # 버퍼 없이 테스트
    
    buy_codes = ["005930", "000660", "035720"]
    signal_df = _make_signal_df({
        "005930": 0.15, "000660": 0.10, "035720": 0.08,
    })
    
    result = calc.calculate(
        buy_codes=buy_codes,
        signal_df=signal_df,
        current_holdings=[],
        available_cash=10_000_000,
        price_map={"005930": 70000, "000660": 150000, "035720": 40000},
        name_map={"005930": "삼성전자", "000660": "SK하이닉스", "035720": "카카오"},
    )
    
    assert len(result.sell_list) == 0, "매도 종목 없어야 함"
    assert len(result.hold_list) == 0, "유지 종목 없어야 함"
    assert len(result.buy_list) == 3, f"매수 3종목이어야 함, got {len(result.buy_list)}"
    
    # 균등 배분: 10,000,000 / 3 ≈ 3,333,333원씩
    for item in result.buy_list:
        assert item.order_qty > 0, f"{item.stock_code} 매수 수량이 0"
        assert item.action == DiffAction.BUY
    
    # 잔여 현금은 floor로 인한 나머지
    assert result.estimated_cash_after >= 0
    assert result.total_buy_value <= 10_000_000
    
    print("✅ 시나리오 1 통과: 신규 진입")
    print(result.summary())


def test_scenario_2_full_liquidation():
    """시나리오 2: 보유 종목 전량 청산 (BUY 시그널 종목과 겹침 없음)"""
    calc = PositionDiffCalculator()
    
    buy_codes = ["035720", "051910"]
    signal_df = _make_signal_df({
        "035720": 0.12, "051910": 0.09,
    })
    
    current_holdings = [
        CurrentHolding("005930", "삼성전자", 100, 70000, 7_000_000),
        CurrentHolding("000660", "SK하이닉스", 20, 150000, 3_000_000),
    ]
    
    result = calc.calculate(
        buy_codes=buy_codes,
        signal_df=signal_df,
        current_holdings=current_holdings,
        available_cash=1_000_000,
        price_map={"035720": 40000, "051910": 100000},
        name_map={"035720": "카카오", "051910": "LG화학"},
    )
    
    assert len(result.sell_list) == 2, "보유 2종목 전량 매도"
    assert len(result.hold_list) == 0, "유지 종목 없어야 함"
    assert len(result.buy_list) == 2, "신규 매수 2종목"
    assert result.total_sell_value == 10_000_000  # 7M + 3M
    
    print("✅ 시나리오 2 통과: 전량 청산 + 신규 매수")
    print(result.summary())


def test_scenario_3_partial_overlap():
    """시나리오 3: 일부 유지 + 일부 청산 + 일부 신규"""
    calc = PositionDiffCalculator(cash_buffer_ratio=0.02)
    
    # 목표: 삼성전자(유지), 카카오(신규) / SK하이닉스(청산)
    buy_codes = ["005930", "035720"]
    signal_df = _make_signal_df({
        "005930": 0.15, "035720": 0.10,
    })
    
    current_holdings = [
        CurrentHolding("005930", "삼성전자", 50, 70000, 3_500_000),
        CurrentHolding("000660", "SK하이닉스", 20, 150000, 3_000_000),
    ]
    
    result = calc.calculate(
        buy_codes=buy_codes,
        signal_df=signal_df,
        current_holdings=current_holdings,
        available_cash=500_000,
        price_map={"005930": 70000, "035720": 40000},
        name_map={"005930": "삼성전자", "000660": "SK하이닉스", "035720": "카카오"},
    )
    
    assert len(result.sell_list) == 1, "SK하이닉스만 매도"
    assert result.sell_list[0].stock_code == "000660"
    assert len(result.hold_list) == 1, "삼성전자 유지"
    assert result.hold_list[0].stock_code == "005930"
    assert len(result.buy_list) == 1, "카카오 신규 매수"
    assert result.buy_list[0].stock_code == "035720"
    
    print("✅ 시나리오 3 통과: 부분 겹침")
    print(result.summary())


def test_scenario_4_zero_qty_excluded():
    """시나리오 4: 고가 종목 → 0주 계산 시 매수 제외"""
    calc = PositionDiffCalculator(cash_buffer_ratio=0.0)
    
    buy_codes = ["005930", "HIGH_PRICE"]
    signal_df = _make_signal_df({
        "005930": 0.15, "HIGH_PRICE": 0.10,
    })
    
    result = calc.calculate(
        buy_codes=buy_codes,
        signal_df=signal_df,
        current_holdings=[],
        available_cash=1_000_000,
        price_map={"005930": 70000, "HIGH_PRICE": 900000},  # 90만원짜리 → 50만원 배분 시 0주
        name_map={"005930": "삼성전자", "HIGH_PRICE": "고가종목"},
    )
    
    # 고가종목은 500,000 / 900,000 = 0주 → 제외
    buy_codes_in_result = [item.stock_code for item in result.buy_list]
    assert "HIGH_PRICE" not in buy_codes_in_result, "0주 종목은 매수 목록에서 제외"
    
    print("✅ 시나리오 4 통과: 0주 종목 제외")
    print(result.summary())


def test_scenario_5_no_buy_signal():
    """시나리오 5: BUY 시그널 없음 → 매수 없이 결과 반환"""
    calc = PositionDiffCalculator()
    
    current_holdings = [
        CurrentHolding("005930", "삼성전자", 100, 70000, 7_000_000),
    ]
    
    result = calc.calculate(
        buy_codes=[],
        signal_df=pd.DataFrame(),
        current_holdings=current_holdings,
        available_cash=3_000_000,
        price_map={},
    )
    
    assert len(result.sell_list) == 1, "보유 종목 전량 매도"
    assert len(result.buy_list) == 0, "매수 없음"
    assert result.estimated_cash_after == 10_000_000  # 3M + 7M
    
    print("✅ 시나리오 5 통과: BUY 시그널 없음")
    print(result.summary())


if __name__ == "__main__":
    test_scenario_1_fresh_entry()
    print()
    test_scenario_2_full_liquidation()
    print()
    test_scenario_3_partial_overlap()
    print()
    test_scenario_4_zero_qty_excluded()
    print()
    test_scenario_5_no_buy_signal()
    print()
    print("🎉 모든 테스트 통과!")