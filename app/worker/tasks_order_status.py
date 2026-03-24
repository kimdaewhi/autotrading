import json
import redis.asyncio as redis

from datetime import datetime, timezone
from decimal import Decimal

from app.broker.kis.kis_auth import KISAuth
from app.broker.kis.kis_order import KISOrder
from app.services.auth_service import AuthService
from app.services.trade_service import TradeService
from app.worker.celery_app import celery_app
from app.worker.runtime import run_async
from app.db.session import AsyncSessionLocal
from app.repository.order_repository import get_order_by_id, update_order_tracking_result
from app.core.constants import (
    ORDER_TRACKING_FAST_WINDOW_SECONDS,
    ORDER_TRACKING_MAX_WINDOW_SECONDS,
    ORDER_TRACKING_SLOW_INTERVAL_SECONDS,
    RETRACKING_INTERVAL_SECONDS,
)
from app.core.enums import ORDER_STATUS
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


def _extract_order_tracking_snapshot(order, service_result) -> dict:
    """
    주식일별주문체결조회 응답(output1)에서
    현재 주문(order.broker_order_no)에 해당하는 1건을 찾아 상태 스냅샷 구성

    상태 판단은 output1의 매칭 row만 기준으로 한다.
    output2는 조회 기준 전체 주문 요약이므로 사용하지 않는다.
    """
    payload = to_dict(service_result)
    output1 = payload.get("output1", [])

    matched_row = None
    for row in output1:
        row_dict = to_dict(row)
        # 핵심 매칭키: broker_order_no == odno
        if str(row_dict.get("odno", "")).strip() == str(order.broker_order_no).strip():
            matched_row = row_dict
            break

    # 조회 성공이지만 해당 주문 row가 아직 안 잡힌 경우
    if matched_row is None:
        return {
            "rt_cd": payload.get("rt_cd"),
            "msg_cd": payload.get("msg_cd"),
            "msg1": payload.get("msg1"),
            "filled_qty": None,
            "unfilled_qty": None,
            "filled_avg_price": None,
            "is_canceled": False,
            "next_status": ORDER_STATUS(order.status),
            "tracking_response_payload": json.dumps(payload, ensure_ascii=False),
        }

    # output1 단건 기준 상태 판정용 필드
    order_qty = to_decimal(matched_row.get("ord_qty")) or Decimal("0")  # 주문 수량
    filled_qty = to_decimal(matched_row.get("tot_ccld_qty")) or Decimal("0") # 총 체결 수량
    unfilled_qty = to_decimal(matched_row.get("rmn_qty")) or Decimal("0") # 잔여 수량
    filled_avg_price = to_decimal(matched_row.get("avg_prvs")) # 평균가
    rejected_qty = to_decimal(matched_row.get("rjct_qty")) or Decimal("0") # 거부 수량
    cncl_yn = str(matched_row.get("cncl_yn", "")).upper()
    is_canceled = cncl_yn == "Y"
    
    # 상태 결정
    if is_canceled:
        next_status = ORDER_STATUS.CANCELED
    elif rejected_qty > 0:
        next_status = ORDER_STATUS.FAILED
    elif filled_qty >= order_qty and order_qty > 0:
        next_status = ORDER_STATUS.FILLED
    elif filled_qty > 0 and unfilled_qty > 0:
        next_status = ORDER_STATUS.PARTIAL_FILLED
    elif filled_qty > 0:
        # 일부 응답에서 rmn_qty가 0이어도 order_qty보다 작으면 부분체결로 보는 방어 로직
        next_status = ORDER_STATUS.PARTIAL_FILLED
    else:
        # 아직 미체결이면 ACCEPTED 유지
        next_status = ORDER_STATUS.ACCEPTED

    return {
        "rt_cd": payload.get("rt_cd"),
        "msg_cd": payload.get("msg_cd"),
        "msg1": payload.get("msg1"),
        "broker_org_no": matched_row.get("ord_gno_brno"),
        "broker_order_no": matched_row.get("odno"),
        "filled_qty": filled_qty,
        "filled_avg_price": filled_avg_price,
        "is_canceled": is_canceled,
        "next_status": next_status,
        "tracking_response_payload": json.dumps(payload, ensure_ascii=False),
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

    if first_tracked_at is None:
        first_tracked_at_dt = now_utc
        first_tracked_at = first_tracked_at_dt.isoformat()
    else:
        first_tracked_at_dt = datetime.fromisoformat(first_tracked_at)

    elapsed_seconds = max((now_utc - first_tracked_at_dt).total_seconds(), 0)
    
    async with AsyncSessionLocal() as db:
        try:
            # 1. 주문 조회
            order = await get_order_by_id(db, order_id)
            if order is None:
                logger.error(f"DB 조회 실패 - 주문이 존재하지 않습니다. order_id : {order_id}")
                return
            order_pk = order.id
            
            # 2. 해당 주문이 추적 대상 상태인지 확인
            if ORDER_STATUS(order.status) not in TRACKING_TARGET_STATUSES:
                logger.info(f"주문 상태 추적 대상 아님. order_id : {order_pk}, status : {order.status}")
                return

            # 3. 주문 번호 확인
            if not order.broker_order_no:
                logger.info(f"주문 번호 존재하지 않음 - 주문 추적 불가. order_id : {order_pk}")
                return
            
            # 4 인증 / 서비스 생성
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
            
            
            # 5. 주문 조회 API 호출
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
            
            # 6. 응답 파싱 및 다음 상태 결정
            snapshot = _extract_order_tracking_snapshot(
                order=order,
                service_result=service_result
            )
            
            # 7. DB 업데이트
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
                next_status=snapshot["next_status"],
                tracking_response_payload=snapshot["tracking_response_payload"],
            )
            if not updated:
                logger.error(f"주문 상태 추적 업데이트 실패. order_id : {order_pk}")
                await db.rollback()
                return
            await db.commit()
            
            logger.info(f"주문 상태 추적 완료. order_id : {order_pk}, next_status : {snapshot['next_status']}")
            
            # 8. 종료 상태 아니면 지연 재큐잉
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
        except Exception as e:
            await db.rollback()
            logger.error(f"주문 상태 추적 실패. order_id : {order_pk or order_id}, error : {str(e)}")
            return
