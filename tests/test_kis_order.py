import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock

from app.core.exceptions import KISOrderError
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
    
    # 브로커 API 호출 및 서비스 로직 실행
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


@pytest.mark.asyncio
async def test_buy_domestic_stock_fail_by_kis_order_error():
    # given
    mock_broker = AsyncMock()
    # KISOrderError 예외를 발생시키도록 설정 (예: 잔고 부족)
    mock_broker.buy_domestic_stock_by_cash.side_effect = KISOrderError(
        message="주문 실패: 잔고 부족",
        status_code=400,
        error_code="40580000",
    )

    service = TradeService(mock_broker)

    # when / then
    with pytest.raises(HTTPException) as exc_info:
        await service.buy_domestic_stock(
            access_token="test-token",
            stock_code="005930",
            quantity="1",
            order_type=OrderType.MARKET,
            price="0",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "주문 실패: 잔고 부족"