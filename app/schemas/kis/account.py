from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# 보유 종목 정보 모델
class HoldingRead(BaseModel):
    stock_code: str             # 종목코드
    stock_name: str             # 종목명
    
    holding_qty: str            # 보유수량
    
    avg_buy_price: str          # 평균 매입 단가
    current_price: str          # 현재가
    
    purchase_amount: str        # 매입금액
    evaluation_amount: str      # 평가금액
    
    profit_loss_amount: str     # 평가손익
    profit_loss_rate: str       # 평가손익률
    
    model_config = ConfigDict(from_attributes=True)


# 계좌 요약 정보 모델
class AccountSummaryRead(BaseModel):
    settlement_cash_amount: str     # D+2 예수금
    stock_evaluation_amount: str    # 주식 평가금액
    total_evaluation_amount: str    # 총 평가금액
    net_asset_amount: str           # 순자산

    total_purchase_amount: str      # 총 매입금액
    total_profit_loss_amount: str   # 총 평가손익
    
    holding_stock_count: str | None = None  # 보유종목 수 (optional)

    model_config = ConfigDict(from_attributes=True)


class AccountDashboardRead(BaseModel):
    account_summary: AccountSummaryRead
    holding_list: list[HoldingRead]

    model_config = ConfigDict(from_attributes=True)