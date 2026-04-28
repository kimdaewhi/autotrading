import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.market.realtime.kis_realtime_client import KISRealtimeClient


# ========================= Fixtures =========================

@pytest.fixture
def client():
    return KISRealtimeClient()


@pytest.fixture
def connected_client(client):
    """WebSocket이 연결된 상태의 클라이언트"""
    client._ws = AsyncMock()
    client._approval_key = "test-approval-key"
    client._running = True
    return client


# ========================= 연결 테스트 =========================

# 🧪 WebSocket 연결 성공 시나리오
@pytest.mark.asyncio
async def test_connect_success(client):
    # given
    mock_ws = AsyncMock()

    with patch.object(client, "_get_approval_key", return_value="test-approval-key") as mock_auth, \
        patch("app.market.realtime.kis_realtime_client.connect", AsyncMock(return_value=mock_ws)) as mock_connect:

        # when
        await client.connect()

        # then
        mock_auth.assert_awaited_once()
        mock_connect.assert_awaited_once()
        assert client._ws is mock_ws
        assert client._approval_key == "test-approval-key"


# 🧪 WebSocket 연결 종료 시나리오
@pytest.mark.asyncio
async def test_disconnect(connected_client):
    # given
    mock_ws = connected_client._ws

    # when
    await connected_client.disconnect()

    # then
    mock_ws.close.assert_awaited_once()
    assert connected_client._ws is None
    assert connected_client._running is False


# ========================= 구독 테스트 =========================

# 🧪 종목 구독 요청 성공 시나리오
@pytest.mark.asyncio
async def test_subscribe_success(connected_client):
    # given
    stock_code = "005930"

    # when
    await connected_client.subscribe(stock_code)

    # then
    connected_client._ws.send.assert_awaited_once()
    sent_message = connected_client._ws.send.call_args[0][0]
    parsed = json.loads(sent_message)

    assert parsed["header"]["approval_key"] == "test-approval-key"
    assert parsed["header"]["tr_type"] == "1"
    assert parsed["body"]["input"]["tr_id"] == "H0STCNT0"
    assert parsed["body"]["input"]["tr_key"] == stock_code
    assert stock_code in connected_client._subscribed_codes


# 🧪 종목 구독 해제 요청 성공 시나리오
@pytest.mark.asyncio
async def test_unsubscribe_success(connected_client):
    # given
    stock_code = "005930"
    connected_client._subscribed_codes.add(stock_code)

    # when
    await connected_client.unsubscribe(stock_code)

    # then
    connected_client._ws.send.assert_awaited_once()
    sent_message = connected_client._ws.send.call_args[0][0]
    parsed = json.loads(sent_message)

    assert parsed["header"]["tr_type"] == "2"
    assert parsed["body"]["input"]["tr_key"] == stock_code
    assert stock_code not in connected_client._subscribed_codes


# 🧪 WebSocket 미연결 상태에서 구독 요청 시 RuntimeError 발생
@pytest.mark.asyncio
async def test_subscribe_without_connection_raises_error(client):
    # given - 연결되지 않은 상태

    # when / then
    with pytest.raises(RuntimeError, match="WebSocket이 연결되지 않았습니다."):
        await client.subscribe("005930")


# ========================= 메시지 처리 테스트 =========================

# 🧪 PINGPONG 메시지 수신 시 동일 메시지 echo 응답
@pytest.mark.asyncio
async def test_on_message_pingpong(connected_client):
    # given
    pingpong_message = json.dumps({
        "header": {"tr_id": "PINGPONG", "datetime": "20260404142023"}
    })

    # when
    await connected_client.on_message(pingpong_message)

    # then - 받은 메시지를 그대로 되돌려 보내야 함
    connected_client._ws.send.assert_awaited_once_with(pingpong_message)


# 🧪 구독 성공 응답 메시지 처리 (로그만 남기고 정상 처리)
@pytest.mark.asyncio
async def test_on_message_subscribe_response_success(connected_client):
    # given
    subscribe_response = json.dumps({
        "header": {"tr_id": "H0STCNT0", "tr_key": "005930", "encrypt": "N"},
        "body": {
            "rt_cd": "0",
            "output": {"msg1": "SUBSCRIBE SUCCESS"}
        }
    })

    # when / then - 예외 없이 정상 처리
    await connected_client.on_message(subscribe_response)


# 🧪 구독 실패 응답 메시지 처리
@pytest.mark.asyncio
async def test_on_message_subscribe_response_failure(connected_client):
    # given
    subscribe_fail = json.dumps({
        "header": {"tr_id": "H0STCNT0", "tr_key": "999999", "encrypt": "N"},
        "body": {
            "rt_cd": "1",
            "output": {"msg1": "SUBSCRIBE FAIL"}
        }
    })

    # when / then - 예외 없이 정상 처리 (경고 로그만 남김)
    await connected_client.on_message(subscribe_fail)


# 🧪 실시간 체결 데이터 수신 시 정상 처리 (파싱 미구현 상태에서 에러 없이 통과)
@pytest.mark.asyncio
async def test_on_message_realtime_data(connected_client):
    # given - "0" 또는 "1"로 시작하는 파이프 구분자 데이터
    realtime_message = "0|H0STCNT0|001|005930^121500^70100^..."

    # when / then - TODO 상태이므로 에러 없이 무시
    await connected_client.on_message(realtime_message)
    connected_client._ws.send.assert_not_awaited()


# 🧪 파싱 불가능한 메시지 수신 시 에러 없이 무시
@pytest.mark.asyncio
async def test_on_message_invalid_json(connected_client):
    # given
    invalid_message = "this is not json and not realtime data"

    # when / then - 경고 로그만 남기고 에러 없이 통과
    await connected_client.on_message(invalid_message)
    connected_client._ws.send.assert_not_awaited()


# ========================= 재연결 테스트 =========================

# 🧪 연결 끊김 후 재연결 시 기존 구독 종목 복구
@pytest.mark.asyncio
async def test_start_resubscribes_on_reconnect(client):
    # given
    client._subscribed_codes = {"005930", "066570"}
    call_count = 0

    async def mock_connect():
        nonlocal call_count
        call_count += 1
        client._approval_key = "test-approval-key"
        client._ws = AsyncMock()
        # 첫 번째 연결: 메시지 하나 받고 종료 → 두 번째 연결: 바로 종료
        if call_count == 1:
            client._ws.__aiter__ = AsyncMock(return_value=iter([]))
        else:
            client._running = False
            client._ws.__aiter__ = AsyncMock(return_value=iter([]))

    with patch.object(client, "connect", side_effect=mock_connect), \
        patch.object(client, "subscribe", new_callable=AsyncMock) as mock_subscribe:

        # when
        await client.start()

        # then - 두 번 연결되므로 종목당 2회씩 구독 요청
        assert mock_subscribe.await_count == 4
        subscribed_codes = {call.args[0] for call in mock_subscribe.await_args_list}
        assert subscribed_codes == {"005930", "066570"}


# 🧪 최대 재연결 시도 초과 시 루프 종료
@pytest.mark.asyncio
async def test_start_stops_after_max_reconnect_attempts(client):
    # given
    client.MAX_RECONNECT_ATTEMPTS = 2
    client.RECONNECT_DELAY_SECONDS = 0  # 테스트 속도를 위해 대기 제거

    with patch.object(client, "connect", side_effect=Exception("connection failed")):

        # when
        await client.start()

        # then - running이 True인 상태에서 max attempts 초과로 종료
        assert client._ws is None