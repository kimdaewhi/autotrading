import httpx
import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock

from app.core.exceptions import KISOrderError
from app.services.kis.trade_service import TradeService
from app.schemas.kis import OrderResponse
from app.core.enums import ORDER_TYPE


# 🧪 매수 주문 성공 시나리오
@pytest.mark.asyncio
async def test_buy_domestic_stock_success():
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
        order_type=ORDER_TYPE.MARKET,
        price="0",
    )
    
    # then
    assert result.rt_cd == "0"
    assert result.output.ODNO == "0000013903"
    assert result.output.KRX_FWDG_ORD_ORGNO == "12345"


# 🧪 매수 주문 실패 시나리오 - 잔고 부족, 매수 금액 오류, 거래 시간 외 주문 등은 모두 동일한 KISOrderError 예외로 처리
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
            order_type=ORDER_TYPE.MARKET,
            price="0",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "주문 실패: 잔고 부족"


# 🧪 매수 주문 실패 시나리오 - 네트워크 오류
@pytest.mark.asyncio
async def test_buy_domestic_stock_fail_by_http_exception():
    # given
    mock_broker = AsyncMock()
    mock_broker.buy_domestic_stock_by_cash.side_effect = httpx.HTTPError("network error")

    service = TradeService(mock_broker)

    # when / then
    with pytest.raises(HTTPException) as exc_info:
        await service.buy_domestic_stock(
            access_token="test-token",
            stock_code="005930",
            quantity="1",
            order_type=ORDER_TYPE.MARKET,
            price="0",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "매수 체결 요청 중 네트워크 오류가 발생했습니다."



# 🧪 매도 주문 성공 시나리오
@pytest.mark.asyncio
async def test_sell_domestic_stock_success():
    # given
    broker_response = OrderResponse(
        rt_cd="0",
        msg_cd="40590000",
        msg1="매도 주문이 성공적으로 체결되었습니다.",
        output={
            "KRX_FWDG_ORD_ORGNO": "12345",
            "ODNO": "0000014011",
            "ORD_TMD": "121500",
            "SOR_ODNO": ""
        }
    )

    mock_broker = AsyncMock()
    mock_broker.sell_domestic_stock_by_cash.return_value = broker_response

    service = TradeService(mock_broker)

    # when
    result = await service.sell_domestic_stock(
        access_token="test-token",
        stock_code="005930",
        quantity="1",
        order_type=ORDER_TYPE.MARKET,
        price="0",
    )

    # then
    assert result.rt_cd == "0"
    assert result.output.ODNO == "0000014011"
    assert result.output.KRX_FWDG_ORD_ORGNO == "12345"


# 🧪 매도 주문 실패 시나리오 - 매도 금액 오류, 보유 수량 부족, 거래 시간 외 부족 등은 모두 동일한 KISOrderError 예외로 처리
@pytest.mark.asyncio
async def test_sell_domestic_stock_fail_by_kis_order_error():
    # given
    mock_broker = AsyncMock()
    mock_broker.sell_domestic_stock_by_cash.side_effect = KISOrderError(
        message="주문 실패: 보유 수량 부족",
        status_code=400,
        error_code="40570000",
    )

    service = TradeService(mock_broker)

    # when / then
    with pytest.raises(HTTPException) as exc_info:
        await service.sell_domestic_stock(
            access_token="test-token",
            stock_code="005930",
            quantity="1",
            order_type=ORDER_TYPE.MARKET,
            price="0",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "주문 실패: 보유 수량 부족"


# 🧪 매도 주문 실패 시나리오 - 네트워크 오류
@pytest.mark.asyncio
async def test_sell_domestic_stock_fail_by_http_error():
    # given
    mock_broker = AsyncMock()
    mock_broker.sell_domestic_stock_by_cash.side_effect = httpx.HTTPError("network error")

    service = TradeService(mock_broker)

    # when / then
    with pytest.raises(HTTPException) as exc_info:
        await service.sell_domestic_stock(
            access_token="test-token",
            stock_code="005930",
            quantity="1",
            order_type=ORDER_TYPE.MARKET,
            price="0",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "매도 체결 요청 중 네트워크 오류가 발생했습니다."


# 🧪 매도 주문 실패 시나리오 - 기타 예외
@pytest.mark.asyncio
async def test_sell_domestic_stock_fail_by_unexpected_error():
    # given
    mock_broker = AsyncMock()
    mock_broker.sell_domestic_stock_by_cash.side_effect = Exception("unexpected error")

    service = TradeService(mock_broker)

    # when / then
    with pytest.raises(HTTPException) as exc_info:
        await service.sell_domestic_stock(
            access_token="test-token",
            stock_code="005930",
            quantity="1",
            order_type=ORDER_TYPE.MARKET,
            price="0",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "매도 주문 처리 중 오류 발생"