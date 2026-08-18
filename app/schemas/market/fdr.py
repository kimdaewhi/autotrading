from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FdrIndexOhlcvRead(BaseModel):
    base_date: str          # 기준일자 (YYYY-MM-DD)
    
    open_price: str         # 시가
    high_price: str         # 고가
    low_price: str          # 저가
    close_price: str        # 종가
    
    up_down: str            # 등락 구분 (1: 상승, 2: 하락)
    change_amount: str      # 전일 대비 증감액 (Comp)
    change_rate: str        # 등락률 (%)
    
    volume: str             # 거래량
    trade_amount: str       # 거래대금 (Amount)
    market_cap: str         # 시가총액 (MarCap)
    
    model_config = ConfigDict(from_attributes=True)