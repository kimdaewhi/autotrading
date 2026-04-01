import json
import redis.asyncio as redis

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.broker.kis.enums import ORD_DVSN_KRX
from app.broker.kis.kis_auth import KISAuth
from app.broker.kis.kis_order import KISOrder
from app.core.exceptions import KISOrderError
from app.db.session import AsyncSessionLocal
from app.domain.order_state import can_transition
from app.services.auth_service import AuthService
from app.worker.celery_app import celery_app
from app.worker.runtime import run_async
from app.worker.tasks_order_status import process_order_status

from app.services.trade_service import TradeService
from app.repository.order_repository import (
    get_order_by_id, 
    update_order_status, 
    update_order_submit_result, 
    update_order_failure_result
)

from app.core.enums import ORDER_ACTION, ORDER_KIND, ORDER_STATUS, ORDER_TYPE
from app.core.settings import settings
from app.utils.logger import get_logger
from app.utils.utils import to_dict

from app.websocket.publisher import publish_order_update


logger = get_logger(__name__)


def _parse_submitted_at(ord_tmd: str | None) -> datetime | None:
    """
    KIS 주문시간(HHMMSS)을 오늘 날짜 기준 Asia/Seoul timestamptz 값으로 변환
    예: "111554" -> 2026-03-23 11:15:54+09:00
    """
    if not ord_tmd:
        return None
    
    try:
        seoul_tz = ZoneInfo("Asia/Seoul")
        now = datetime.now(seoul_tz)
        parsed_time = datetime.strptime(ord_tmd, "%H%M%S").time()
        return datetime.combine(now.date(), parsed_time, tzinfo=seoul_tz)
    except ValueError:
        return None




def _extract_order_snapshot(service_result: Any, order_qty: Any) -> dict[str, Any]:
    """
    Broker 응답을 파싱해서 [주문번호, 체결수량, 상태(next_status)] 등을 결정하는 핵심 로직
    - service_result: Broker API로부터 받은 주문 체결 응답 객체
    - order_qty: 원래 주문한 수량 (주문 체결 결과에서 체결 수량과 비교하기 위해 필요)
    """
    root_payload = to_dict(service_result)
    
    # 응답 payload에서 필요한 정보 추출
    output = to_dict(root_payload.get("output"))

    rt_cd = root_payload.get("rt_cd")
    msg_cd = root_payload.get("msg_cd")
    msg1 = root_payload.get("msg1")

    broker_org_no = output.get("KRX_FWDG_ORD_ORGNO")
    broker_order_no = output.get("ODNO")
    ord_tmd = output.get("ORD_TMD")
    submitted_at = _parse_submitted_at(ord_tmd)
    
    if str(rt_cd) != "0":
        next_status = ORDER_STATUS.FAILED
    elif broker_order_no:
        next_status = ORDER_STATUS.ACCEPTED
    else:
        next_status = ORDER_STATUS.REQUESTED
    
    return {
        "rt_cd": rt_cd,
        "msg_cd": msg_cd,
        "msg1": msg1,
        "broker_org_no": broker_org_no,
        "broker_order_no": broker_order_no,
        "submitted_at": submitted_at,
        "submit_response_payload": json.dumps(root_payload, default=str, ensure_ascii=False),
        "next_status": next_status,
        # 주문이 접수되었거나 요청이 성공적으로 처리된 경우에는 남은 수량을 원래 주문 수량으로 설정, 그렇지 않은 경우에는 0으로 설정
        "remaining_qty": int(order_qty) if next_status in [ORDER_STATUS.REQUESTED, ORDER_STATUS.ACCEPTED] else 0,
    }


# 주문 실패가 rate limit 초과에 의한 것인지 판별하는 함수.
def is_rate_limit_error(e: KISOrderError) -> bool:
    response = (e.payload or {}).get("response", {})
    original_msg_cd = response.get("msg_cd")
    original_msg1 = response.get("msg1") or e.msg1 or ""
    
    return (
        original_msg_cd == "EGW00201"
        or "초당 거래건수" in original_msg1
    )


@celery_app.task(name="app.worker.tasks_order.process_order")
def process_order(order_id: str) -> None:    
    run_async(_process_order(order_id))

# TODO : 앱 재기동/장애 복구 시 stadle order 정합성 복구 배치 필요
# - 대상 예시)
#   - PENDING 상태로 오래 머문 주문
#   - PROCESSING/REQUESTED/ACCEPTED 상태에서 중단된 주문
#   - REQUESTED/ACCEPTED 상태인데, 상태 추적(worker-2)이 끊어진 주문
# - 처리 방향:
#   - 단순 FAILED 일괄 처리 보다는 주문 시각, 장운영 시간, broker_order_no 존재 여부 기준으로 정책 수립 필요
#   - 별도 recovery task(startup job 또는 periodic batch)로 구현
# - 책임 위치:
#   - worker-1 / worker-2 내부가 아닌 별도 복구 작업으로 분리
async def _process_order(order_id: str) -> None:
    """
    1차 워커
    - 주문 요청
    - 주문 접수 결과 반영
    """
    order_pk = None # order_id로 조회가 안되는 경우를 대비해서 order_pk로 캐싱
    
    async with AsyncSessionLocal() as db:
        try:
            # 1. DB에서 order_id 조회
            order = await get_order_by_id(db, order_id)
            if order is None:
                logger.error(f"DB 조회 실패 - 주문이 존재하지 않습니다. order_id : {order_id}")
                return
            order_pk = order.id
            
            # 2. PENDING 상태 확인 및 PROCESSING 상태로 전이(다른 워커가 이미 처리 중인 경우에는 상태 업데이트 실패 처리)
            updated = await update_order_status(db=db, order_id=order_pk, expected_current_statuses=[ORDER_STATUS.PENDING], new_status=ORDER_STATUS.PROCESSING)
            if not updated:
                logger.warning(f"이미 다른 워커가 처리 중이거나 상태가 변경됨. order_id={order_id}")
                return
            await db.commit()
            
            # 3. access token 발급을 위한 인증 서비스 및 TradeService 인스턴스 생성
            redis_client = redis.from_url(settings.CELERY_BROKER_URL, decode_responses=False)
            auth_service = AuthService(
                auth_broker=KISAuth(
                    appkey=settings.KIS_APP_KEY,
                    appsecret=settings.KIS_APP_SECRET,
                    url=f"{settings.kis_base_url}",
                ),
                redis_client=redis_client,
            )
            access_token = await auth_service.get_valid_access_token()
            
            trade_service = TradeService(kis_order=KISOrder(
                appkey=settings.KIS_APP_KEY, 
                appsecret=settings.KIS_APP_SECRET, 
                url=f"{settings.kis_base_url}"
                )
            )
            
            # 4. Broker 주문 체결 API 요청(실제 주문)            
            # 신규 주문(매수/매도), 정정 주문, 취소 주문에 따라 분기처리
            if order.order_kind == ORDER_KIND.NEW.value:
                if order.order_pos == ORDER_ACTION.BUY.value:
                    service_result = await trade_service.buy_domestic_stock(
                        access_token=access_token,
                        stock_code=order.stock_code,
                        quantity=str(order.order_qty),
                        order_type=ORDER_TYPE(order.order_type),
                        price=str(order.order_price),
                    )
                elif order.order_pos == ORDER_ACTION.SELL.value:
                    service_result = await trade_service.sell_domestic_stock(
                        access_token=access_token,
                        stock_code=order.stock_code,
                        quantity=str(order.order_qty),
                        order_type=ORDER_TYPE(order.order_type),
                        price=str(order.order_price),
                    )
                else:
                    raise ValueError(f"알 수 없는 주문 포지션입니다. order_id : {order_id}, order_pos : {order.order_pos}")
            # 정정 주문
            elif order.order_kind == ORDER_KIND.MODIFY.value:
                if not order.original_order_id:
                    raise ValueError(f"[정정] 원주문 정보가 존재하지 않습니다. order_id : {order_id}")
                if not order.original_broker_order_no:
                    raise ValueError(f"[정정] 원주문 브로커 주문번호가 존재하지 않습니다. order_id : {order_id}")
                if not order.original_broker_org_no:
                    raise ValueError(f"[정정] 원주문 브로커 조직번호가 존재하지 않습니다. order_id : {order_id}")
                if order.order_qty <= 0:
                    raise ValueError(f"[정정] 정정 주문 수량은 0보다 커야합니다. order_id : {order_id}, order_qty : {order.order_qty}")
                
                original_order = await get_order_by_id(db, order.original_order_id)
                if not original_order:
                    raise ValueError(f"[정정] 원주문을 찾을 수 없습니다. order_id : {order_id}, original_order_id : {order.original_order_id}")
                if original_order.remaining_qty <= 0:
                    raise ValueError(f"[정정] 원주문 잔량이 없어 정정할 수 없습니다. order_id : {order_id}, original_order_id : {order.original_order_id}, remaining_qty : {original_order.remaining_qty}")
                if order.order_qty > original_order.remaining_qty:
                    raise ValueError(f"[정정] 정정 주문 수량이 원주문 잔량보다 많습니다. order_id : {order_id}, order_qty : {order.order_qty}, original_order_remaining_qty : {original_order.remaining_qty}")
                
                is_full_modify = order.order_qty >= original_order.remaining_qty
                
                service_result = await trade_service.revise_domestic_stock(
                    access_token=access_token,
                    order_no=order.original_broker_order_no,
                    quantity=str(order.order_qty),
                    # DB에 시장가면 시장가 코드, 지정가면 지정가 코드로 한투 API 스펙에 맞게 변환해서 전달
                    order_type=ORDER_TYPE.MARKET if order.order_type == ORDER_TYPE.MARKET.value else ORDER_TYPE.LIMIT,
                    price=str(order.order_price),
                    krx_fwdg_ord_orgno=order.original_broker_org_no,
                    qty_all_order_yn="Y" if is_full_modify else "N",
                )
            # 취소 주문
            elif order.order_kind == ORDER_KIND.CANCEL.value:
                if not order.original_order_id:
                    raise ValueError(f"[취소] 원주문 정보가 존재하지 않습니다. order_id : {order_id}")
                if not order.original_broker_order_no:
                    raise ValueError(f"[취소] 원주문 브로커 주문번호가 존재하지 않습니다. order_id : {order_id}")
                if not order.original_broker_org_no:
                    raise ValueError(f"[취소] 원주문 브로커 조직번호가 존재하지 않습니다. order_id : {order_id}")
                if order.order_qty <= 0:
                    raise ValueError(f"[취소] 취소 주문 수량은 0보다 커야합니다. order_id : {order_id}, order_qty : {order.order_qty}")
                
                original_order = await get_order_by_id(db, order.original_order_id)
                if not original_order:
                    raise ValueError(f"[취소] 원주문을 찾을 수 없습니다. order_id : {order_id}, original_order_id : {order.original_order_id}")
                if original_order.remaining_qty <= 0:
                    raise ValueError(f"[취소] 원주문 잔량이 없어 취소할 수 없습니다. order_id : {order_id}, original_order_id : {order.original_order_id}, remaining_qty : {original_order.remaining_qty}")
                if order.order_qty > original_order.remaining_qty:
                    raise ValueError(f"[취소] 취소 주문 수량이 원주문 잔량보다 많습니다. order_id : {order_id}, order_qty : {order.order_qty}, original_order_remaining_qty : {original_order.remaining_qty}")
                
                is_full_cancel = order.order_qty >= original_order.remaining_qty
                
                service_result = await trade_service.cancel_domestic_stock(
                    access_token=access_token,
                    order_no=order.original_broker_order_no,
                    krx_fwdg_ord_orgno=order.original_broker_org_no,
                    quantity=str(order.order_qty),
                    qty_all_order_yn="Y" if is_full_cancel else "N",
                    order_type=ORD_DVSN_KRX.MARKET.value        # 취소 주문은 가격을 지정하지 않으므로, 시장가로 고정
                )
            else:
                raise ValueError(f"알 수 없는 주문 종류입니다. order_id : {order_id}, order_kind : {order.order_kind}")
            
            # 5. 응답 전문 Parse 및 상태 결정
            snapshot = _extract_order_snapshot(service_result=service_result, order_qty=order.order_qty)
            
            # 상태전이 체크
            current_status = order.status
            next_status = snapshot["next_status"].value
            
            if not can_transition(current_status, next_status):
                logger.error(f"허용되지 않은 상태 전이 감지(worker-1). "f"order_id : {order_pk}, current_status : {current_status}, next_status : {next_status}")
                await db.rollback()
                return
            
            # 6. 주문 결과에 따라 Order ORM 업데이트 (주문 번호, 체결 수량, 상태(next_status) 등)
            updated = await update_order_submit_result(
                db=db, 
                order_id=order_pk, 
                rt_cd=snapshot["rt_cd"],
                msg_cd=snapshot["msg_cd"],
                msg1=snapshot["msg1"],
                broker_org_no=snapshot["broker_org_no"], 
                broker_order_no=snapshot["broker_order_no"], 
                submitted_at=snapshot["submitted_at"],
                submit_response_payload=snapshot["submit_response_payload"], 
                next_status=snapshot["next_status"],
                remaining_qty=snapshot["remaining_qty"],
            )
            
            # 7. DB 커밋
            if not updated:
                await db.rollback()
                logger.error(f"주문 결과 업데이트 실패 - 상태가 예상과 다릅니다. order_id={order_pk}")
                return
            await db.commit()
            # 🟢 주문상태 변경 브로드케스트
            await publish_order_update(db, order_pk)
            
            logger.info(f"주문 처리 완료. order_id : {order_pk}, next_status : {snapshot['next_status'].value}, broker_order_no : {snapshot['broker_order_no']}, broker_org_no : {snapshot['broker_org_no']}")
            
            if snapshot["next_status"] in [ORDER_STATUS.ACCEPTED, ORDER_STATUS.REQUESTED]:
                # 주문이 접수되었으므로 주문 상태 추적 태스크 등록
                process_order_status.delay(str(order_pk))
            
        except KISOrderError as e:
            await db.rollback()
            
            # rate limit 발생으로 인한 실패인 경우, 주문 상태를 FAILED로 업데이트 하지 않고 재큐잉 처리
            if is_rate_limit_error(e):
                logger.warning(f"주문 처리 실패 - API rate limit 초과. 주문을 재시도합니다. order_id={order_pk}, rt_cd={e.rt_cd}, msg_cd={e.msg_cd}, msg1={e.msg1}")
                await update_order_status(db=db, order_id=order_pk, expected_current_statuses=[ORDER_STATUS.PROCESSING], new_status=ORDER_STATUS.PENDING)
                await db.commit()
                process_order.apply_async(args=[order_id], countdown=60)  # 60초 후에 재시도
                return
            
            # KISOrderError는 주문 실패를 의미하므로, 주문 상태를 FAILED로 업데이트
            if order_pk is not None:
                await update_order_failure_result(
                    db=db,
                    order_id=order_pk,
                    rt_cd=e.rt_cd or "1",
                    msg_cd=e.msg_cd or "KIS_ORDER_ERROR",
                    msg1=e.msg1 or e.message,
                    next_status=ORDER_STATUS.FAILED,
                    response_payload=json.dumps(
                        e.payload if e.payload is not None else {
                            "rt_cd": e.rt_cd,
                            "msg_cd": e.msg_cd,
                            "msg1": e.msg1,
                            "message": e.message,
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                )
                await db.commit()
                # 🟢 주문상태 변경 브로드케스트
                await publish_order_update(db, order_pk)
            logger.error(f"주문 처리 실패(브로커). order_id={order_pk}, "f"rt_cd={e.rt_cd}, msg_cd={e.msg_cd}, msg1={e.msg1}")
            return
        except Exception as e:
            await db.rollback()
            
            error_message = str(e)
            if order_pk is not None:
                await update_order_failure_result(
                    db=db,
                    order_id=order_pk,
                    rt_cd="ERROR",
                    msg_cd="WORKER_EXCEPTION",
                    msg1=error_message,
                    next_status=ORDER_STATUS.FAILED,
                    response_payload=json.dumps(
                        {
                            "error": error_message,
                            "order_id": str(order_pk),
                            "stage": "process_order",
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                )
                await db.commit()
                # 🟢 주문상태 변경 브로드케스트
                await publish_order_update(db, order_pk)
            logger.error(f"주문 처리 실패. order_id={order_pk}, error={error_message}")
            return