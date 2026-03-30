import json
import redis.asyncio as redis

from datetime import datetime, timezone
from decimal import Decimal

from app.broker.kis.kis_auth import KISAuth
from app.broker.kis.kis_order import KISOrder
from app.core.exceptions import KISOrderError
from app.db.models.order import Order
from app.services.auth_service import AuthService
from app.services.trade_service import TradeService
from app.worker.celery_app import celery_app
from app.worker.runtime import run_async
from app.db.session import AsyncSessionLocal
from app.repository.order_repository import (
    exists_child_orders,
    get_order_by_id, 
    update_order_failure_result, 
    update_order_tracking_result,
    update_parent_order_after_child
)
from app.core.constants import (
    ORDER_TRACKING_FAST_WINDOW_SECONDS,
    ORDER_TRACKING_MAX_WINDOW_SECONDS,
    ORDER_TRACKING_SLOW_INTERVAL_SECONDS,
    RETRACKING_INTERVAL_SECONDS,
)
from app.core.enums import ORDER_KIND, ORDER_STATUS
from app.core.settings import settings
from app.utils.logger import get_logger
from app.utils.utils import to_dict, to_decimal


logger = get_logger(__name__)

TRACKING_TARGET_STATUSES = {
    ORDER_STATUS.REQUESTED,
    ORDER_STATUS.ACCEPTED,
    ORDER_STATUS.PARTIAL_FILLED,
}

# 주문 상태 중에서 최종 상태(체결 완료, 주문 실패, 주문 취소 등)로 간주되는 상태 집합
TERMINAL_STATUSES = {
    ORDER_STATUS.FAILED,
    ORDER_STATUS.FILLED,
    ORDER_STATUS.CANCELED,
}


def _resolve_retracking_delay(attempt: int, elapsed_seconds: float) -> int | None:
    """
    다음 재추적까지 대기 시간을 계산한다.
    - 빠른 구간: 1초 시작, 점진적 backoff(최대 15초)
    - 느린 구간: 60초 간격
    - 최대 추적 구간 초과 시 None 반환(재큐잉 중단)
    """
    if elapsed_seconds >= ORDER_TRACKING_MAX_WINDOW_SECONDS:
        return None

    if elapsed_seconds < ORDER_TRACKING_FAST_WINDOW_SECONDS:
        return min(RETRACKING_INTERVAL_SECONDS * (attempt + 1), 15)

    return ORDER_TRACKING_SLOW_INTERVAL_SECONDS


def _extract_order_tracking_snapshot(
    order: Order,
    service_result: dict,
    has_child_orders: bool = False,
) -> dict:
    """
    주식일별주문체결조회 응답(output1)에서
    현재 주문(order.broker_order_no)에 해당하는 1건을 찾아 상태 스냅샷 구성
    
    상태 판단은 output1의 매칭 row만 기준으로 한다.
    output2는 조회 기준 전체 주문 요약이므로 사용하지 않는다.
    상태 판정 기준
    - FILLED:
        총 체결 수량이 주문 수량 이상인 경우
    - PARTIAL_FILLED:
        일부만 체결되고 잔량이 남아있는 경우
    - CANCELED:
        미체결 주문이 전량 취소된 경우
        또는 일부 체결 후 나머지 취소가 완료되어 주문이 종료된 경우
        또는 (보조 시그널)cncl_yn = Y 인 취소/정정 자식 주문인 경우
    - FAILED:
        거부 수량이 존재하는 경우
    - ACCEPTED:
        아직 체결/취소/실패로 확정되지 않은 경우
    """
    payload = to_dict(service_result)
    output1 = payload.get("output1", [])
    
    matched_row = None
    for row in output1:
        row_dict = to_dict(row)
        if str(row_dict.get("odno", "")).strip() == str(order.broker_order_no).strip():
            matched_row = row_dict
            break
    
    # 조회 성공이지만 해당 주문 row가 아직 안 잡힌 경우
    if matched_row is None:
        return {
            "rt_cd": payload.get("rt_cd"),
            "msg_cd": payload.get("msg_cd"),
            "msg1": payload.get("msg1"),
            "broker_org_no": order.broker_org_no,
            "broker_order_no": order.broker_order_no,
            "filled_qty": int(order.filled_qty or 0),
            "remaining_qty": int(order.remaining_qty or 0),
            "filled_avg_price": order.avg_fill_price,
            "is_canceled": False,
            "next_status": ORDER_STATUS(order.status),
            "tracking_response_payload": json.dumps(payload, ensure_ascii=False),
        }
    
    # output1 단건 기준 상태 판정용 필드
    order_qty = int(to_decimal(matched_row.get("ord_qty")) or Decimal("0"))
    row_remaining_qty = int(to_decimal(matched_row.get("rmn_qty")) or Decimal("0"))
    cancel_confirm_qty = int(to_decimal(matched_row.get("cncl_cfrm_qty")) or Decimal("0"))
    rejected_qty = int(to_decimal(matched_row.get("rjct_qty")) or Decimal("0"))
    filled_avg_price = to_decimal(matched_row.get("avg_prvs"))

    # 핵심:
    # 부모/자식 공통으로 filled_qty는 ord_qty - 잔량 - 취소확인 - 거부 로 계산
    # 음수 방지
    row_filled_qty = max(order_qty - row_remaining_qty - cancel_confirm_qty - rejected_qty, 0)
    
    # 체인 주문 정책:
    # 부모 NEW 주문에 자식 주문이 이미 존재하는 경우,
    # 부모 output1 row의 rmn_qty는 "현재 시장에 살아있는 최종 잔량"을 보장하지 않는다.
    # 따라서 이 경우 부모의 filled_qty / remaining_qty는 브로커 row로 재계산하지 않고
    # DB에 누적 반영된 현재 값을 신뢰한다.
    if order.order_kind == ORDER_KIND.NEW.value and has_child_orders:
        # 부모 NEW 주문에 자식 주문이 존재하는 경우,
        # 부모 row의 rmn_qty를 기준으로 현재 유효 잔량을 판단한다.
        # DB 누적값을 그대로 신뢰하면 stale 값으로 부모 상태를 덮어쓸 수 있으므로,
        # 이 경우에는 브로커 row의 잔량을 우선 반영한다.
        remaining_qty = row_remaining_qty
        filled_qty = max(order_qty - remaining_qty - cancel_confirm_qty - rejected_qty, 0)

        # 평균 체결가는 부모 row에 안 잡힐 수 있으므로 기존 DB 값 유지
        filled_avg_price = order.avg_fill_price

        parent_state = _resolve_parent_after_child(
            parent_order_qty=order_qty,
            parent_filled_qty=filled_qty,
            parent_remaining_qty=remaining_qty,
        )
        next_status = parent_state["next_status"]
    else:
        filled_qty = row_filled_qty
        remaining_qty = row_remaining_qty

        # 상태 결정
        # TODO : rejected_qty의 경우 느슨하게 판정할지, 엄격하게 판정할지에 대한 정책 설계 필요(현재는 rejected_qty가 0이 아닌 경우를 보지 못함)
        # if rejected_qty > 0:
        #     next_status = ORDER_STATUS.FAILED
        
        # 전량 체결 (정정 자식 주문 포함)
        # ord_qty와 잔량(rmn_qty)로 종료를 함께 확인해 조기 FILLED 오판정을 줄인다.
        if order_qty > 0 and filled_qty >= order_qty and remaining_qty == 0:
            next_status = ORDER_STATUS.FILLED
        
        # 미체결 전량 취소 / 일부 체결 후 잔량 취소 모두 CANCELED로 귀결
        elif (
            order_qty > 0
            and filled_qty == 0
            and cancel_confirm_qty >= order_qty
            and remaining_qty == 0
        ):
            next_status = ORDER_STATUS.CANCELED
        
        # 일부 체결 후 잔량이 남아있는 경우는 PARTIAL_FILLED
        elif remaining_qty > 0:
            if filled_qty > 0:
                next_status = ORDER_STATUS.PARTIAL_FILLED
            else:
                next_status = ORDER_STATUS.ACCEPTED
        
        else:
            # remaining_qty == 0 이면 종료 상태
            if filled_qty >= order_qty and order_qty > 0:
                next_status = ORDER_STATUS.FILLED
            elif cancel_confirm_qty > 0:
                # 미체결 전량취소 / 일부체결 후 잔량취소 모두 포함
                next_status = ORDER_STATUS.CANCELED
            elif rejected_qty > 0:
                next_status = ORDER_STATUS.FAILED
            elif filled_qty > 0:
                # 방어적으로 부분체결 종료 상태는 CANCELED로 귀결
                next_status = ORDER_STATUS.CANCELED
            else:
                next_status = ORDER_STATUS.ACCEPTED
    
    return {
        "rt_cd": payload.get("rt_cd"),
        "msg_cd": payload.get("msg_cd"),
        "msg1": payload.get("msg1"),
        "broker_org_no": matched_row.get("ord_gno_brno"),
        "broker_order_no": matched_row.get("odno"),
        "order_qty": order_qty,
        "filled_qty": filled_qty,
        "remaining_qty": remaining_qty,
        "cancel_confirm_qty": cancel_confirm_qty,
        "rejected_qty": rejected_qty,
        "filled_avg_price": filled_avg_price,
        "next_status": next_status,
        "tracking_response_payload": json.dumps(payload, ensure_ascii=False),
    }


def _is_retryable_tracking_error(e: Exception) -> bool:
    """
    주문 상태 추적 중 발생한 오류가 일시적인 네트워크/서버 문제로 인한 것인지 판별
    - KISOrderError의 msg_cd, msg1을 분석하여 rate limit 초과, 서버 오류, 타임아웃 등 일시적 문제 여부 판단
    - 일반 Exception의 경우 메시지에 "timeout", "temporarily unavailable", "connection" 등이 포함되어 있는지 확인
    - 이 함수는 재추적 재큐잉 여부 결정에 사용된다.
    - KISOrderError라도 주문 실패를 의미하는 명확한 오류 메시지가 있는 경우에는 False를 반환하여 주문 실패로 처리하도록 한다.
    """
    if isinstance(e, KISOrderError):
        msg_cd = getattr(e, "msg_cd", None)
        msg1 = (getattr(e, "msg1", None) or getattr(e, "message", "") or "").strip()
        
        if msg_cd == "EGW00201":
            return True
        if "초당 거래건수" in msg1:
            return True
        if "Server error: 500" in msg1:
            return True
        if "timeout" in msg1.lower():
            return True
        if "temporarily unavailable" in msg1.lower():
            return True
    
    error_text = str(e).lower()
    return (
        "server error: 500" in error_text
        or "timeout" in error_text
        or "connection" in error_text
        or "temporarily unavailable" in error_text
    )


def _requeue_order_tracking(order_pk, attempt: int, first_tracked_at: str, elapsed_seconds: float) -> bool:
    """
    주문 상태 추적을 재큐잉한다.
    - 다음 재추적까지 대기 시간 계산: 빠른 구간(0-30초)은 점진적 backoff, 느린 구간(30초 이상)은 60초 간격
    - 최대 추적 구간(10분) 초과 시 재큐잉 중단
    """
    next_delay_seconds = _resolve_retracking_delay(
        attempt=attempt,
        elapsed_seconds=elapsed_seconds,
    )
    if next_delay_seconds is None:
        logger.warning(
            "주문 상태 추적 재시도 중단(최대 추적 시간 초과). "
            f"order_id : {order_pk}, attempt : {attempt}, elapsed_seconds : {elapsed_seconds:.1f}"
        )
        return False
    
    logger.warning(
        "주문 상태 추적 일시 실패 - 재큐잉. "
        f"order_id : {order_pk}, next_attempt : {attempt + 1}, "
        f"countdown_seconds : {next_delay_seconds}, elapsed_seconds : {elapsed_seconds:.1f}"
    )
    process_order_status.apply_async(
        kwargs={
            "order_id": str(order_pk),
            "attempt": attempt + 1,
            "first_tracked_at": first_tracked_at,
        },
        countdown=next_delay_seconds,
    )
    return True



# def _resolve_parent_terminal_status(
#     parent_order_qty: int, 
#     parent_filled_qty: int, 
#     parent_remaining_qty: int
# ) -> ORDER_STATUS:
#     """
#     자식 주문(취소/정정) 처리 결과를 반영하여 원주문(parent)의 다음 상태를 계산한다.
#     - parent_remaining_qty > 0 이면 아직 활성 주문으로 간주한다.
#     - parent_remaining_qty == 0 이면 종료 상태로 간주한다.
#     - 정정 주문의 경우 호출부에서 parent_remaining_qty=0 으로 전달하여 부모 종료를 표현한다.
#     """
#     # remaining_qty > 0 이면 아직 활성 주문
#     if parent_remaining_qty > 0:
#         return (
#             ORDER_STATUS.PARTIAL_FILLED
#             if parent_filled_qty > 0
#             else ORDER_STATUS.ACCEPTED
#         )

#     # remaining_qty == 0 이면 부모는 종료 상태
#     if parent_filled_qty >= parent_order_qty and parent_order_qty > 0:
#         return ORDER_STATUS.FILLED

#     # 미체결 전량 취소 / 부분체결 후 잔량 소멸 / 정정으로 대체
#     return ORDER_STATUS.CANCELED


def _resolve_parent_after_child(
    parent_order_qty: int,
    parent_filled_qty: int,
    parent_remaining_qty: int,
) -> dict:
    """
    자식 주문 결과를 반영하여 부모 주문의 다음 filled_qty, remaining_qty, status 계산
    """
    
    # 주문수량과 체결수량이 같아지면 부모 주문 == 체결 완료
    if parent_filled_qty >= parent_order_qty and parent_order_qty > 0:
        next_status = ORDER_STATUS.FILLED
    
    # 잔량이 남아있으면 아직 활성 주문
    elif parent_remaining_qty > 0:
        next_status = ( ORDER_STATUS.PARTIAL_FILLED if parent_filled_qty > 0 else ORDER_STATUS.ACCEPTED )
    else:
        next_status = ORDER_STATUS.CANCELED
    
    return {
        "filled_qty": parent_filled_qty,
        "remaining_qty": parent_remaining_qty,
        "next_status": next_status,
    }


@celery_app.task(name="app.worker.tasks_order_status.process_order_status")
def process_order_status(order_id: str, attempt: int = 0, first_tracked_at: str | None = None) -> None:
    logger.info(
        f"주문 상태 추적 큐 등록. order_id : {order_id}, attempt : {attempt}, first_tracked_at : {first_tracked_at}"
    )
    run_async(_process_order_status(order_id, attempt, first_tracked_at))


async def _process_order_status(order_id: str, attempt: int = 0, first_tracked_at: str | None = None) -> None:
    order_pk = None
    now_utc = datetime.now(timezone.utc)

    # ⌚ 이 구간은 aggresive polling + adaptive backoff + low-frequency polling을 처리하여 재큐잉 여부를 결정하는 구간
    if first_tracked_at is None:
        first_tracked_at_dt = now_utc
        first_tracked_at = first_tracked_at_dt.isoformat()
    else:
        first_tracked_at_dt = datetime.fromisoformat(first_tracked_at)

    elapsed_seconds = max((now_utc - first_tracked_at_dt).total_seconds(), 0)
    
    async with AsyncSessionLocal() as db:
        try:
            # ⭐ 1. 주문 조회
            order = await get_order_by_id(db, order_id)
            if order is None:
                logger.error(f"DB 조회 실패 - 주문이 존재하지 않습니다. order_id : {order_id}")
                return
            order_pk = order.id
            
            # ⭐ 2. 해당 주문이 추적 대상 상태인지 확인
            if ORDER_STATUS(order.status) not in TRACKING_TARGET_STATUSES:
                logger.info(f"주문 상태 추적 대상 아님. order_id : {order_pk}, status : {order.status}")
                return
            
            # ⭐ 3. 주문 번호 확인
            if not order.broker_order_no:
                logger.info(f"주문 번호 존재하지 않음 - 주문 추적 불가. order_id : {order_pk}")
                return
            
            # ⭐ 4. 인증 / 서비스 생성
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
                url=f"{settings.kis_base_url}",
            ))
            
            
            # ⭐ 5. 주문 조회 API 호출
            service_result = await trade_service.get_daily_order_executions(
                access_token=access_token,
                account_no=order.account_no,
                account_product_code=order.account_product_code,
                start_date=order.created_at.strftime("%Y%m%d"),
                end_date=order.created_at.strftime("%Y%m%d"),
                stock_code=order.stock_code,
                broker_org_no=order.broker_org_no,
                broker_order_no=order.broker_order_no,
            )
            
            # ⭐ 6. 응답 파싱 및 다음 상태 결정
            # 원주문의 자식 주문이 chain으로 존재하는 경우 발생하는 chain reaction의 일관성을 위해, 
            # 부모 주문이면서 자식 주문이 존재하는 경우에는 부모 주문의 output1 row 상태를 신뢰하지 않고 
            # DB에 누적된 filled_qty/remaining_qty를 우선적으로 반영한다.
            has_child_orders = False
            if order.order_kind == ORDER_KIND.NEW.value:
                has_child_orders = await exists_child_orders(db, order.id)
    
            snapshot = _extract_order_tracking_snapshot(
                order=order,
                service_result=service_result,
                has_child_orders=has_child_orders,
            )
            
            # ⭐ 7. DB 업데이트
            updated = await update_order_tracking_result(
                db=db,
                order_id=order_pk,
                rt_cd=snapshot["rt_cd"],
                msg_cd=snapshot["msg_cd"],
                msg1=snapshot["msg1"],
                broker_org_no=snapshot["broker_org_no"],
                broker_order_no=snapshot["broker_order_no"],
                filled_qty=snapshot["filled_qty"],
                filled_avg_price=snapshot["filled_avg_price"],
                remaining_qty=snapshot["remaining_qty"],
                next_status=snapshot["next_status"],
                tracking_response_payload=snapshot["tracking_response_payload"],
            )
            
            if not updated:
                logger.error(f"주문 상태 추적 업데이트 실패. order_id : {order_pk}")
                await db.rollback()
                return
            
            
            # ⭐ 8. 취소/정정 주문이면 원주문 상태도 함께 업데이트
            if order.original_order_id:
                parent_order = None
                # -----------------------------
                # 🔴 8-1. CANCEL
                # -----------------------------
                # 취소 자식 주문은 "체결 수량"이 아니라
                # "이번 추적 사이클 동안 실제 새로 반영된 취소 수량(delta_cancel_qty)"만큼만
                # 부모 remaining_qty를 줄여야 한다.
                #
                # 이유:
                # - 취소 주문은 첫 조회 시점에 이미 remaining_qty=0 으로 들어올 수 있다.
                # - 따라서 previous_remaining_qty - current_remaining_qty 방식만으로는
                #   실제 취소 반영 수량을 놓칠 수 있다.
                # - 취소 자식 주문의 누적 반영 수량을 기준으로 delta를 계산해야
                #   중복 반영 없이 부모 잔량을 안정적으로 갱신할 수 있다
                if (
                    order.order_kind == ORDER_KIND.CANCEL.value
                    and snapshot["next_status"] in {
                        ORDER_STATUS.CANCELED,
                        ORDER_STATUS.FILLED,
                        ORDER_STATUS.PARTIAL_FILLED,
                    }
                ):
                    parent_order = await get_order_by_id(db, order.original_order_id)
                    if parent_order is None:
                        raise ValueError(f"원주문을 찾을 수 없습니다. original_order_id={order.original_order_id}")
                    
                    previous_applied_cancel_qty = int(order.filled_qty or 0)
                    current_applied_cancel_qty = max(
                        int(snapshot["order_qty"] or 0)
                        - int(snapshot["remaining_qty"] or 0)
                        - int(snapshot["rejected_qty"] or 0),
                        0,
                    )
                    
                    # 이번 추적 사이클 동안 새로 반영된 취소 수량
                    delta_cancel_qty = max(current_applied_cancel_qty - previous_applied_cancel_qty, 0)
                    
                    # 실제로 새로 취소 확정된 수량이 있을 때만 부모 잔량 반영
                    if delta_cancel_qty > 0:
                        new_parent_remaining_qty = max(
                            int(parent_order.remaining_qty or 0) - delta_cancel_qty,
                            0,
                        )
                        
                        parent_next = _resolve_parent_after_child(
                            parent_order_qty=int(parent_order.order_qty or 0),
                            parent_filled_qty=int(parent_order.filled_qty or 0),
                            parent_remaining_qty=new_parent_remaining_qty,
                        )
                        
                        updated_parent = await update_parent_order_after_child(
                            db=db,
                            order_id=parent_order.id,
                            filled_qty=parent_next["filled_qty"],
                            remaining_qty=parent_next["remaining_qty"],
                            next_status=parent_next["next_status"],
                        )
                        if not updated_parent:
                            logger.error(f"[취소] 원주문 상태 업데이트 실패. original_order_id : {parent_order.id}")
                            await db.rollback()
                            return
                        
                # -----------------------------
                # 🔵 8-2. MODIFY
                # -----------------------------
                # 정정 자식 주문은 ACCEPTED 되었다고 해서 원주문이 즉시 종료되지 않는다.
                # 부분 정정/부분 체결이 가능하므로, 부모 주문은 자식 주문에서
                # "이번 추적 사이클 동안 실제 새로 체결된 수량(delta_filled_qty)"만큼만 반영한다.
                elif (
                    order.order_kind == ORDER_KIND.MODIFY.value
                    and snapshot["next_status"] in {
                        ORDER_STATUS.PARTIAL_FILLED,
                        ORDER_STATUS.FILLED,
                    }
                ):
                    parent_order = await get_order_by_id(db, order.original_order_id)
                    if parent_order is None:
                        raise ValueError(f"[정정] 원주문을 찾을 수 없습니다. original_order_id={order.original_order_id}")
                    
                    previous_child_filled_qty = int(order.filled_qty or 0)
                    current_child_filled_qty = int(snapshot["filled_qty"] or 0)
                    
                    # 이번 추적 사이클 동안 새로 증가한 체결 수량
                    delta_filled_qty = max(current_child_filled_qty - previous_child_filled_qty, 0)
                    
                    # 실제로 새로 체결된 수량이 있을 때만 부모 반영
                    if delta_filled_qty > 0:
                        parent_order_qty = int(parent_order.order_qty or 0)
                        parent_prev_filled_qty = int(parent_order.filled_qty or 0)
                        parent_prev_remaining_qty = int(parent_order.remaining_qty or 0)
                        
                        new_parent_filled_qty = min(
                            parent_prev_filled_qty + delta_filled_qty,
                            parent_order_qty,
                        )
                        new_parent_remaining_qty = max(
                            parent_prev_remaining_qty - delta_filled_qty,
                            0,
                        )
                        
                        parent_next = _resolve_parent_after_child(
                            parent_order_qty=parent_order_qty,
                            parent_filled_qty=new_parent_filled_qty,
                            parent_remaining_qty=new_parent_remaining_qty,
                        )
                        
                        updated_parent = await update_parent_order_after_child(
                            db=db,
                            order_id=parent_order.id,
                            filled_qty=parent_next["filled_qty"],
                            remaining_qty=parent_next["remaining_qty"],
                            next_status=parent_next["next_status"],
                        )
                        if not updated_parent:
                            logger.error(f"[정정] 원주문 상태 업데이트 실패. original_order_id : {parent_order.id}")
                            await db.rollback()
                            return
            
            await db.commit()
            logger.info(f"주문 상태 추적 완료. order_id : {order_pk}, next_status : {snapshot['next_status']}")
            
            # 최종 체결 로그
            prev_filled_qty = int(order.filled_qty or 0)
            curr_filled_qty = int(snapshot["filled_qty"] or 0)
            if snapshot["next_status"] == ORDER_STATUS.FILLED:
                logger.info(f"주문 체결 완료. order_id : {order_pk}, 주문 수량 : {order.order_qty}, 체결 수량 : {snapshot['filled_qty']}, 평균 체결가 : {snapshot['filled_avg_price']}")
            elif snapshot["next_status"] == ORDER_STATUS.PARTIAL_FILLED and curr_filled_qty > prev_filled_qty:
                logger.info(f"주문 부분 체결. order_id : {order_pk}, 주문 수량 : {order.order_qty}, 체결 수량 : {snapshot['filled_qty']}, 잔여 수량 : {snapshot['remaining_qty']}, 평균 체결가 : {snapshot['filled_avg_price']}")
            
            
            # ⭐ 9. 종료 상태 아니면 지연 재큐잉
            if snapshot["next_status"] not in TERMINAL_STATUSES:
                next_delay_seconds = _resolve_retracking_delay(
                    attempt=attempt,
                    elapsed_seconds=elapsed_seconds,
                )
                if next_delay_seconds is None:
                    logger.warning(
                        "주문 상태 추적 종료(최대 추적 시간 초과). "
                        f"order_id : {order_pk}, elapsed_seconds : {elapsed_seconds:.1f}, status : {snapshot['next_status']}"
                    )
                    return
                
                logger.info(
                    "주문 미종료 - 재추적 재큐잉. "
                    f"order_id : {order_pk}, current_status : {snapshot['next_status']}, "
                    f"next_attempt : {attempt + 1}, countdown_seconds : {next_delay_seconds}, elapsed_seconds : {elapsed_seconds:.1f}"
                )
                process_order_status.apply_async(
                    kwargs={
                        "order_id": str(order_pk),
                        "attempt": attempt + 1,
                        "first_tracked_at": first_tracked_at,
                    },
                    countdown=next_delay_seconds,
                )
        except KISOrderError as e:
            await db.rollback()
            
            # 주문 상태 추적 중 발생한 오류가 일시적인 네트워크/서버 문제로 인한 것인지 판별하여 재큐잉 여부 결정
            if _is_retryable_tracking_error(e):
                logger.warning(
                    "주문 상태 추적 중 일시적 브로커 오류 발생. "
                    f"order_id={order_id}, msg_cd={e.msg_cd}, msg1={e.msg1 or e.message}"
                )
                _requeue_order_tracking(
                    order_pk=order_pk,
                    attempt=attempt,
                    first_tracked_at=first_tracked_at,
                    elapsed_seconds=elapsed_seconds,
                )
                return
            
            # KISOrderError는 주문 실패를 의미하므로, 주문 상태를 FAILED로 업데이트
            if order_pk is not None:
                await update_order_failure_result(
                    db=db,
                    order_id=order_pk,
                    rt_cd=e.rt_cd or "1",
                    msg_cd=e.msg_cd or "KIS_TRACKING_ERROR",
                    msg1=e.msg1 or e.message,
                    next_status=ORDER_STATUS.FAILED,
                    response_payload=json.dumps(
                        e.payload if e.payload is not None else {
                            "rt_cd": e.rt_cd,
                            "msg_cd": e.msg_cd,
                            "msg1": e.msg1,
                            "message": e.message,
                            "stage": "process_order_status",
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                )
                await db.commit()
                
            logger.error(f"KIS 주문 상태 추적 중 오류 발생 - 주문 실패로 간주. order_id={order_id}, error={str(e)}")
            return
        except Exception as e:
            await db.rollback()
            
            # 주문 상태 추적 중 발생한 오류가 일시적인 네트워크/서버 문제로 인한 것인지 판별하여 재큐잉 여부 결정
            if _is_retryable_tracking_error(e):
                logger.warning(f"주문 상태 추적 중 일시적 예외 발생. order_id={order_id}, error={str(e)}")
                _requeue_order_tracking(
                    order_pk=order_pk,
                    attempt=attempt,
                    first_tracked_at=first_tracked_at,
                    elapsed_seconds=elapsed_seconds,
                )
                return
            
            # 일반 예외는 주문 상태 추적 실패로 간주하여 주문 상태를 FAILED로 업데이트
            if order_pk is not None:
                await update_order_failure_result(
                    db=db,
                    order_id=order_pk,
                    rt_cd="1",
                    msg_cd="ORDER_TRACKING_ERROR",
                    msg1=str(e),
                    next_status=ORDER_STATUS.FAILED,
                    response_payload=json.dumps({
                        "message": str(e),
                        "stage": "process_order_status",
                    }, ensure_ascii=False),
                )
                await db.commit()
            logger.error(f"주문 상태 추적 실패. order_id={order_id}, error={str(e)}")
            return