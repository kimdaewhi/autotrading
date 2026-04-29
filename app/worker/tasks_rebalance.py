"""자동 리밸런싱 Celery 태스크.

매일 09:00경 Celery beat에 의해 트리거되며, 다음 흐름으로 실행된다:
1. 분산락 획득 (#8) - 동시 실행 방지
2. 직전 리밸런싱 일자 조회 - RebalanceWindow에 주입할 last_rebalance_date
3. 윈도우 체크 (#9) - 영업일/시간대 검증
4. 같은 달 중복 실행 체크 - idempotency
5. RebalanceOrchestrator.run() 호출 - 수동 라우터와 동일 진입점
6. 성공/실패 알림

사전 게이트(1~4)는 모두 통과해야 본 실행으로 진입한다.
어느 게이트라도 막히면 조용히 종료(혹은 알림만)하고 다음 영업일을 기다린다.

TODO(P2/안전): kill switch 정책 점검 후 게이트 0번으로 추가
"""

from __future__ import annotations

import redis.asyncio as redis
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.settings import settings
from app.db.session import AsyncSessionLocal
from app.repository.rebalance_repository import (
    get_last_completed_rebalance_date,
    has_completed_rebalance_in_month,
)
from app.api.router_strategy import get_default_strategy
from app.services.rebalance.rebalance_orchestrator import RebalanceOrchestrator
from app.utils.discord import send_order_error_alert_sync
from app.utils.distributed_lock import (
    LockAcquisitionError,
    distributed_lock,
)
from app.utils.logger import get_logger
from app.utils.market_calendar import (
    KrxCalendar,
    RebalanceWindow,
    SystemClock,
    WindowDecision,
)
from app.worker.celery_app import celery_app
from app.worker.runtime import run_async


logger = get_logger(__name__)

KST = ZoneInfo("Asia/Seoul")

# 분산락 설정
# - 키: 월 1회 리밸런싱이라 단일 키로 충분 (월별 분리 불필요 — 같은 달 중복은 idempotency가 따로 막음)
# - TTL: 리밸런싱 실측 약 3분. 안전 마진으로 10분(600초) 잡음.
#        주문 수가 늘어 5분 이상 걸리는 게 일상화되면 재조정.
REBALANCE_LOCK_KEY = "lock:rebalance:auto"
REBALANCE_LOCK_TTL_SECONDS = 600


@celery_app.task(name="app.worker.tasks_rebalance.execute_rebalance")
def execute_rebalance(dry_run: bool = False, force: bool = False) -> None:
    """자동 리밸런싱 태스크 진입점 (동기).
    
    Args:
        dry_run: True면 실제 주문 없이 시뮬레이션만. 자동 실행에서는 기본 False.
        force: True면 같은 달 중복 실행 체크 우회. 운영 중 수동 재실행 시 사용.
        (분산락과 윈도우 체크는 우회하지 않음 — 그건 진짜 안전장치)
    """
    run_async(_execute_rebalance(dry_run=dry_run, force=force))


async def _execute_rebalance(dry_run: bool, force: bool) -> None:
    """자동 리밸런싱 본체 (async)."""
    redis_client = redis.from_url(settings.CELERY_BROKER_URL, decode_responses=False)
    
    # ⭐ 게이트 1: 분산락 획득 (#8)
    # 이미 다른 인스턴스가 돌고 있으면 LockAcquisitionError → 조용히 종료
    try:
        async with distributed_lock(
            redis_client,
            key=REBALANCE_LOCK_KEY,
            ttl_seconds=REBALANCE_LOCK_TTL_SECONDS,
        ):
            await _execute_under_lock(dry_run=dry_run, force=force)
    except LockAcquisitionError:
        logger.info(
            "자동 리밸런싱 스킵 - 다른 인스턴스가 이미 실행 중. "
            f"key : {REBALANCE_LOCK_KEY}"
        )
        return


async def _execute_under_lock(dry_run: bool, force: bool) -> None:
    """분산락 획득 후 본 실행 흐름.
    
    게이트 2~4를 모두 통과하면 orchestrator.run() 호출.
    """
    async with AsyncSessionLocal() as db:
        # ⭐ 게이트 2: 직전 리밸런싱 일자 조회 → 윈도우 체크 (#9)
        last_rebalance_date = await get_last_completed_rebalance_date(db)
        if last_rebalance_date is None:
            # 첫 자동 실행이면 이력이 없음. 이 경우 자동 실행을 진행하면 안 됨
            # (수동으로 한 번 돌려서 기준점을 만든 뒤 자동이 이어받는 흐름이 안전)
            logger.warning(
                "자동 리밸런싱 스킵 - 직전 성공 리밸런싱 이력이 없음. "
                "수동으로 첫 리밸런싱을 실행한 후 자동을 활성화하세요."
            )
            return
        
        calendar = KrxCalendar()
        clock = SystemClock()
        window = RebalanceWindow(
            calendar=calendar,
            clock=clock,
            last_rebalance_date=last_rebalance_date,
        )
        decision = window.decide()
        
        if decision != WindowDecision.RUN_REBALANCE:
            logger.info(
                "자동 리밸런싱 스킵 - 실행 윈도우 조건 미충족. "
                f"decision : {decision.name}, last_rebalance_date : {last_rebalance_date}"
            )
            return
        
        # ⭐ 게이트 3: 같은 달 중복 실행 체크 (idempotency)
        if not force:
            today_kst = datetime.now(KST).date()
            already_done = await has_completed_rebalance_in_month(db, today_kst)
            if already_done:
                logger.warning(
                    "자동 리밸런싱 스킵 - 이번 달에 이미 실행됨. "
                    f"target_month : {today_kst.year}-{today_kst.month:02d}"
                )
                return
        
        # ⭐ 게이트 4: 기타 조건 체크
        # Kill Switch 체크(정책 점검 후)
        
        # ⭐ 모든 게이트 통과 → 본 실행
        logger.info(
            "자동 리밸런싱 시작. "
            f"last_rebalance_date : {last_rebalance_date}, dry_run : {dry_run}, force : {force}"
        )
        
        try:
            strategy = get_default_strategy()
            orchestrator = RebalanceOrchestrator(strategy)
            
            # year=None: orchestrator 내부에서 _infer_latest_available_fiscal_year() 사용
            result = await orchestrator.run(db=db, year=None, dry_run=dry_run)
            
            # 성공 / 실패 분기
            if result.rebalance_result.success:
                logger.info(
                    "자동 리밸런싱 완료. "
                    f"rebalance_id : {result.rebalance_result.rebalance_id}, "
                    f"strategy : {result.strategy_result.strategy_name}, "
                    f"universe_count : {result.rebalance_result.universe_count}, "
                    f"signal_buy_count : {result.rebalance_result.signal_buy_count}, "
                    f"summary : {result.rebalance_result.summary()}"
                )
            else:
                # 정책: "실패 시 알림 후 멈춤". 자동 재시도 없음.
                logger.error(
                    "자동 리밸런싱 실패 - orchestrator가 실패 결과 반환. "
                    f"rebalance_id : {result.rebalance_result.rebalance_id}, "
                    f"error_message : {result.rebalance_result.error_message}"
                )
                # TODO(P2/알림): 리밸런싱 전용 알림 채널 분리. 현재는 주문 에러 알림 함수 재사용.
                send_order_error_alert_sync(
                    stock_code="-",
                    stock_name="자동 리밸런싱",
                    order_id=str(result.rebalance_result.rebalance_id or "-"),
                    order_action="REBALANCE",
                    error_message=(
                        f"자동 리밸런싱 실패. "
                        f"error : {result.rebalance_result.error_message}"
                    ),
                )
                
        except Exception as e:
            # 예외 발생: orchestrator가 예외를 던진 경우 (DB 트랜잭션은 orchestrator 내부에서 관리)
            logger.error(
                f"자동 리밸런싱 실패 - 예외 발생. error : {str(e)}",
                exc_info=True,
            )
            send_order_error_alert_sync(
                stock_code="-",
                stock_name="자동 리밸런싱",
                order_id="-",
                order_action="REBALANCE",
                error_message=f"자동 리밸런싱 실패 - 예외. error : {str(e)}",
            )
            # 예외는 재발생시키지 않음 (Celery 자동 재시도 방지 — 정책: 실패 시 멈춤)
            return