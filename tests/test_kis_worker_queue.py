import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.core.enums import ORDER_STATUS, ORDER_TYPE
from app.worker.tasks_order import _process_order


@pytest.mark.asyncio
async def test_process_order_buy_success(monkeypatch):
    # given
    order_uuid = uuid.uuid4()
    
    # DB에서 조회되는 주문 레코드의 속성을 가진 가짜 객체 생성
    fake_order = SimpleNamespace(
        id=order_uuid,
        status=ORDER_STATUS.PENDING,
        order_pos="buy",
        stock_code="005930",
        order_qty=5,
        order_type=ORDER_TYPE.LIMIT.value,
        order_price="190000.0000",
    )
    
    # ----------------------------------------
    # 1. DB 세션 mock 만들기
    # ----------------------------------------
    # session_mock:
    # 실제 AsyncSession 대신 사용할 가짜 객체
    # commit(), rollback() 같은 메서드 호출 여부를 검사
    session_mock = AsyncMock()
    
    # cm_mock:
    # "async with AsyncSessionLocal() as db:" 를 흉내내기 위한 객체
    # 즉 context manager 역할
    cm_mock = MagicMock()
    cm_mock.__aenter__ = AsyncMock(return_value=session_mock)
    cm_mock.__aexit__ = AsyncMock(return_value=None)
    
    # monkeypatch:
    # 테스트 중에 "진짜 코드"를 "가짜 코드(mock)"로 잠깐 바꿔치기하는 기능
    
    # 여기서는 AsyncSessionLocal()을 호출하면
    # 진짜 DB 세션이 아니라 위에서 만든 cm_mock이 나오도록 바꿈
    monkeypatch.setattr(
        "app.worker.tasks_order.AsyncSessionLocal",
        MagicMock(return_value=cm_mock),
    )
    
    # ----------------------------------------
    # 2. get_order_by_id mock
    # ----------------------------------------
    # 워커가 DB에서 주문을 조회할 때
    # 실제 DB 조회 대신 fake_order를 바로 돌려주게 함
    monkeypatch.setattr(
        "app.worker.tasks_order.get_order_by_id",
        AsyncMock(return_value=fake_order),
    )
    
    # ----------------------------------------
    # 3. update_order_status mock
    # ----------------------------------------
    # 상태 업데이트 함수도 실제 DB UPDATE를 하지 않고
    # True를 반환하도록 만듦
    #
    # side_effect=[True, True]
    # -> 첫 번째 호출 결과 True
    # -> 두 번째 호출 결과 True
    #
    # 보통
    # 1) PENDING -> PROCESSING
    # 2) PROCESSING -> REQUESTED
    # 이 두 번 성공했다고 가정하는 것
    monkeypatch.setattr(
        "app.worker.tasks_order.update_order_status",
        AsyncMock(side_effect=[True, True]),
    )
    
    # ----------------------------------------
    # 4. KISAuth mock
    # ----------------------------------------
    # 실제 한투 인증 API를 호출하지 않도록
    # "토큰 발급 성공"처럼 보이게 가짜 객체를 만듦
    auth_instance = MagicMock()
    auth_instance.get_access_token = AsyncMock(
        return_value=SimpleNamespace(access_token="mock-token")
    )
    monkeypatch.setattr(
        "app.worker.tasks_order.KISAuth",
        MagicMock(return_value=auth_instance),
    )
    
    # ----------------------------------------
    # 5. TradeService mock
    # ----------------------------------------
    # 실제 주문 요청 API를 호출하지 않도록
    # "주문 성공 응답"을 가짜로 만듦
    trade_service_instance = MagicMock()
    trade_service_instance.buy_domestic_stock = AsyncMock(
        return_value=SimpleNamespace(
            rt_cd="0",
            msg_cd="40600000",
            msg1="모의투자 매수주문이 완료 되었습니다.",
            output=SimpleNamespace(
                KRX_FWDG_ORD_ORGNO="00950",
                ODNO="0000013903",
                ORD_TMD="111554",
                SOR_ODNO="",
            ),
        )
    )
    monkeypatch.setattr(
        "app.worker.tasks_order.TradeService",
        MagicMock(return_value=trade_service_instance),
    )

    monkeypatch.setattr(
        "app.worker.tasks_order.KISOrder",
        MagicMock(),
    )
    
    # ----------------------------------------
    # 7. 실제 테스트 대상 실행
    # ----------------------------------------
    # _process_order를 직접 호출해서
    # 워커 로직이 정상적으로 끝까지 도는지 확인
    await _process_order(str(order_uuid))
    
    # ----------------------------------------
    # 8. 검증
    # ----------------------------------------
    # 매수 주문 함수가 정확히 1번 호출됐는지 확인
    trade_service_instance.buy_domestic_stock.assert_awaited_once()
    
    # commit이 최소 2번 이상 호출됐는지 확인
    # 보통:
    # 1) PROCESSING 반영
    # 2) REQUESTED 반영
    assert session_mock.commit.await_count >= 2