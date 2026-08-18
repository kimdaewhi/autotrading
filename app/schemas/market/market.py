from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MarketIndexRead(BaseModel):
    """ 시장 지수 응답 스키마 """
    name: str               # 지수명 (KOSPI, KOSDAQ)
    base_date: str          # 기준일자 (YYYY-MM-DD)
    close_price: str        # 종가
    change_amount: str      # 전일 대비 증감액
    change_rate: str        # 등락률 (%)

    model_config = ConfigDict(from_attributes=True)