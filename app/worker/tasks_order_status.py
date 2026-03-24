import asyncio
import json
import redis.asyncio as redis

from decimal import Decimal

from app.broker.kis.kis_auth import KISAuth
from app.broker.kis.kis_order import KISOrder
from app.services.auth_service import AuthService
from app.services.trade_service import TradeService
from app.worker.celery_app import celery_app
from app.worker.runtime import run_async
from app.db.session import AsyncSessionLocal
from app.repository.order_repository import get_order_by_id, update_order_tracking_result
from app.core.constants import RETRACKING_INTERVAL_SECONDS, MAX_RETRACKING_COUNT
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
def process_order_status(order_id: str) -> None:
    logger.info(f"주문 상태 추적 큐 등록. order_id : {order_id}")
    run_async(_process_order_status(order_id))


async def _process_order_status(order_id: str) -> None:
    order_pk = None
    
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
            
            # 8. 종료 상태 아니면 재조회
            if snapshot["next_status"] not in TERMINAL_STATUSES:
                logger.info(f"주문 미종료 - 재추적 필요. order_id : {order_pk}, current_status : {snapshot['next_status']}")
                # ⭐⭐⭐ 재추적 간격은 고정 1초로 일단 설정. 추후에 주문 상태나 시간대에 따른 가변 간격 로직 추가 고려
                # TODO: 추후에 Celery 재큐잉 방식으로 변경 고려
                retracking_count = 0
                max_retracking_count = MAX_RETRACKING_COUNT  # 최대 재추적 횟수
                while snapshot["next_status"] not in TERMINAL_STATUSES and retracking_count < max_retracking_count:
                    await asyncio.sleep(RETRACKING_INTERVAL_SECONDS)  # 1초 대기
                    retracking_count += 1
                    logger.info(f"주문 상태 재추적 시도. order_id : {order_pk}, 재시도 : {retracking_count}")
                    
                    # 재조회 API 호출
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
                    
                    # 응답 파싱 및 상태 업데이트
                    snapshot = _extract_order_tracking_snapshot(
                        order=order,
                        service_result=service_result
                    )
                    
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
                        logger.error(f"주문 상태 추적 업데이트 실패 during retracking. order_id : {order_pk}, attempt : {retracking_count}")
                        await db.rollback()
                        return
                    await db.commit()
                    
                    logger.info(f"주문 상태 재추적 완료. order_id : {order_pk}, attempt : {retracking_count}, next_status : {snapshot['next_status']}")
        except Exception as e:
            await db.rollback()
            logger.error(f"주문 상태 추적 실패. order_id : {order_pk or order_id}, error : {str(e)}")
            return