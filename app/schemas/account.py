from __future__ import annotations

from decimal import Decimal
from pydantic import BaseModel, ConfigDict


# 보유 종목 정보 모델
class HoldingRead(BaseModel):
    stock_code: str             # 종목코드
    stock_name: str             # 종목명
    
    holding_qty: int            # 보유수량
    orderable_qty: int          # 주문가능수량
    
    avg_buy_price: Decimal     # 평균 매입 단가
    current_price: Decimal     # 현재가
    
    purchase_amount: Decimal   # 매입금액
    evaluation_amount: Decimal # 평가금액
    
    profit_loss_amount: Decimal   # 평가손익
    profit_loss_rate: Decimal     # 평가손익률
    
    weight_rate: Decimal          # 비중
    
    model_config = ConfigDict(from_attributes=True)


# 계좌 요약 정보 모델
class AccountSummaryRead(BaseModel):
    cash_amount: Decimal                 # 예수금
    stock_evaluation_amount: Decimal    # 주식 평가금액
    total_evaluation_amount: Decimal    # 총 평가금액
    net_asset_amount: Decimal           # 순자산

    total_purchase_amount: Decimal      # 총 매입금액
    total_profit_loss_amount: Decimal   # 총 평가손익

    asset_change_amount: Decimal        # 전일 대비 자산 증감
    asset_change_rate: Decimal          # 전일 대비 자산 증감률

    model_config = ConfigDict(from_attributes=True)


# 당일 거래 요약 정보 모델
class TodayTradingSummaryRead(BaseModel):
    today_buy_amount: Decimal          # 당일 매수 금액
    today_sell_amount: Decimal         # 당일 매도 금액

    today_buy_qty: int                 # 당일 매수 수량
    today_sell_qty: int                # 당일 매도 수량

    model_config = ConfigDict(from_attributes=True)


# 보유 종목 통계 모델
class HoldingStatsRead(BaseModel):
    holding_stock_count: int           # 보유 종목 수
    total_holding_qty: int             # 총 보유 수량
    model_config = ConfigDict(from_attributes=True)


# 수익/손실 상위 종목 모델
class TopHoldingPairRead(BaseModel):
    top_profit_holding: HoldingRead | None   # 최고 수익 종목
    top_loss_holding: HoldingRead | None     # 최고 손실 종목

    model_config = ConfigDict(from_attributes=True)


# 최종 대시보드 응답
class AccountDashboardRead(BaseModel):
    summary: AccountSummaryRead           # 계좌 요약 정보
    holding_stats: HoldingStatsRead       # 보유 종목 통계
    today_trading: TodayTradingSummaryRead  # 당일 거래 요약

    holdings: list[HoldingRead]           # 보유 종목 목록
    profit_holdings: list[HoldingRead]   # 수익 종목 목록
    loss_holdings: list[HoldingRead]     # 손실 종목 목록
    sellable_holdings: list[HoldingRead] # 매도 가능 종목 목록

    top_holdings: TopHoldingPairRead     # 수익/손실 상위 종목

    model_config = ConfigDict(from_attributes=True)