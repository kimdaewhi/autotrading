import pytest
from datetime import datetime
from unittest.mock import AsyncMock
import random

from app.services.trade_service import TradeService
from app.schemas.kis import OrderResponse
from app.core.enums import OrderType

@pytest.mark.asyncio
async def test_buy_domestic_stock_success():
    # curr_time = datetime.now().strftime("%H%M%S")
    # odno = f"00000{random.randint(0, 99999):05d}"

    # given(준비)
    broker_response = OrderResponse(
        rt_cd="0",
        msg_cd="40600000",
        msg1="매수 주문이 성공적으로 체결되었습니다.",
        output={
            "KRX_FWDG_ORD_ORGNO": "12345",
            "ODNO": "0000013903",
            "ORD_TMD": "120000",
            "SOR_ODNO": ""
        }
    )
    
    # 서비스에서 
    mock_broker = AsyncMock()
    mock_broker.buy_domestic_stock_by_cash.return_value = broker_response
    
    service = TradeService(mock_broker)
    
    # when
    result = await service.buy_domestic_stock(
        access_token="test-token",
        stock_code="005930",
        quantity="1",
        order_type=OrderType.MARKET,
        price="0",
    )
    
    # then
    assert result.rt_cd == "0"
    assert result.output.ODNO == "0000013903"
    assert result.output.KRX_FWDG_ORD_ORGNO == "12345"