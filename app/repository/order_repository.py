from datetime import datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import func, update, select
from sqlalchemy.ext.asyncio import AsyncSession
from collections.abc import Sequence

from app.db.models.order import Order
from app.core.enums import ORDER_ACTION, ORDER_STATUS

async def create_order(db: AsyncSession, order_data: dict) -> Order:
    """
    주문 레코드 생성 및 DB 저장
    """
    new_order = Order(**order_data)
    
    db.add(new_order)
    await db.flush()  # 새로 생성된 객체의 ID를 가져오기 위해 flush() 호출
    await db.refresh(new_order)  # 새로 생성된 객체의 상태를 최신으로 유지하기 위해 refresh() 호출
    
    return new_order


# ================================ 주문 조회 관련 메서드 ================================ #
# ⚙️ 모든 주문 레코드 조회
async def get_all_orders(db: AsyncSession) -> list[Order]:
    """
    모든 주문 레코드 조회
    """
    stmt = select(Order).order_by(Order.created_at.desc())
    result = await db.execute(stmt)
    
    return result.scalars().all()


# ⚙️ 특정 상태의 주문 레코드 조회
async def get_orders_by_status(db: AsyncSession, status: str) -> list[Order]:
    """
    특정 상태의 주문 레코드 조회
    """
    stmt = select(Order).where(Order.status == status).order_by(Order.created_at.desc())
    result = await db.execute(stmt)
    
    return result.scalars().all()


# ⚙️ 특정 종목의 주문 레코드 조회
async def get_orders_by_symbol(db: AsyncSession, stock_code: str) -> list[Order]:
    """
    특정 종목의 주문 레코드 조회
    """
    stmt = select(Order).where(Order.stock_code == stock_code).order_by(Order.created_at.desc())
    result = await db.execute(stmt)
    
    return result.scalars().all()


# ⚙️ 매매 방향(매수/매도)으로 주문 레코드 조회(신규 주문만)
async def get_orders_by_order_action(db: AsyncSession, order_action: str) -> list[Order]:
    """
    특정 주문 방향(매수/매도/취소/정정)의 주문 레코드 조회
    """
    stmt = (
        select(Order)
        .where(
            Order.order_pos == order_action,
            Order.order_kind == "new"
        )
        .order_by(Order.created_at.desc()))
    result = await db.execute(stmt)
    
    return result.scalars().all()


# ⚙️ 주문 ID로 주문 레코드 조회
async def get_order_by_id(db: AsyncSession, order_id: UUID) -> Order | None:
    """
    주문 ID로 주문 레코드 조회
    """
    stmt = select(Order).where(Order.id == order_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ================================ 주문지 상태 업데이트 관련 메서드 ================================ #

# ⚙️ 주문 상태 업데이트
async def update_order_status(db: AsyncSession, order_id: UUID, expected_current_statuses: Sequence[ORDER_STATUS], new_status: ORDER_STATUS,) -> bool:
    """
    주문 상태 업데이트
    - order_id에 해당하는 주문 레코드의 상태가 expected_current_statuses 중 하나인 경우에만 new_status로 업데이트
    """
    stmt = (
        update(Order)
        .where(
            Order.id == order_id,
            Order.status.in_([status.value for status in expected_current_statuses]),
        )
        .values(
            status=new_status.value,
            updated_at=func.now(),
        )
    )
    result = await db.execute(stmt)
    return result.rowcount > 0


# ⚙️ 주문 체결 결과 업데이트
async def update_order_submit_result(
    db: AsyncSession, 
    order_id: UUID, 
    rt_cd: str, 
    msg_cd: str, 
    msg1: str, 
    broker_org_no: str, 
    broker_order_no: str, 
    submitted_at: datetime, 
    submit_response_payload: str, 
    next_status: ORDER_STATUS,
    remaining_qty: int | None = None
) -> bool:
    """
    주문 체결 결과 업데이트
    - 주문이 체결된 경우 broker_org_no, broker_order_no, submit_response_payload 등의 필드를 업데이트하고 next_status로 상태 전이
    """
    values = {
        "rt_cd": rt_cd,
        "msg_cd": msg_cd,
        "msg1": msg1,
        "broker_org_no": broker_org_no,
        "broker_order_no": broker_order_no,
        "submitted_at": submitted_at,
        "submit_response_payload": submit_response_payload,
        "status": next_status.value,
        "updated_at": func.now(),
    }
    if remaining_qty is not None:
        values["remaining_qty"] = remaining_qty
    
    stmt = (
        update(Order)
        .where(Order.id == order_id, Order.status == ORDER_STATUS.PROCESSING.value)
        .values(
            # rt_cd=rt_cd,
            # msg_cd=msg_cd,
            # msg1=msg1,
            # broker_org_no=broker_org_no,
            # broker_order_no=broker_order_no,
            # submitted_at=submitted_at,
            # submit_response_payload=submit_response_payload,
            # status=next_status.value,
            # updated_at=func.now(),
            **values
        )
    )
    result = await db.execute(stmt)
    return result.rowcount > 0


# ⚙️ 주문 상태 추적 결과 업데이트
async def update_order_tracking_result(
    db: AsyncSession, 
    order_id: UUID, 
    rt_cd: str, 
    msg_cd: str, 
    msg1: str, 
    broker_org_no: str, 
    broker_order_no: str, 
    filled_qty: int, 
    filled_avg_price: Decimal | None, 
    remaining_qty: int,
    next_status: ORDER_STATUS, 
    tracking_response_payload: str
) -> bool:
    """
    주문 상태 추적 결과 업데이트
    - 주문 상태 추적 결과에 따라 주문 레코드의 체결 수량(filled_qty), 미체결 수량(unfilled_qty), 체결 평균 가격(filled_avg_price) 등을 업데이트하고 next_status로 상태 전이
    """
    stmt = (
        update(Order)
        .where(Order.id == order_id)
        .values(
            rt_cd=rt_cd,
            msg_cd=msg_cd,
            msg1=msg1,
            broker_org_no=broker_org_no,
            broker_order_no=broker_order_no,
            filled_qty=filled_qty,
            remaining_qty=remaining_qty,
            avg_fill_price=filled_avg_price,
            error_message=msg1 if next_status == ORDER_STATUS.FAILED else None,
            submit_response_payload=tracking_response_payload,
            status=next_status.value,
            updated_at=func.now(),
        )
    )
    result = await db.execute(stmt)
    return result.rowcount > 0


# ⚙️ 주문 실패 결과 업데이트
async def update_order_failure_result(
    db: AsyncSession,
    order_id: UUID,
    rt_cd: str,
    msg_cd: str,
    msg1: str,
    next_status: ORDER_STATUS = ORDER_STATUS.FAILED,
    broker_org_no: str | None = None,
    broker_order_no: str | None = None,
    request_payload: str | None = None,
    response_payload: str | None = None,
) -> bool:
    """
    주문 실패 결과 업데이트
    - 주문 제출/처리 단계에서 실패한 경우 공통으로 사용
    - error_message를 반드시 저장
    """
    values_to_update = {
        "rt_cd": rt_cd,
        "msg_cd": msg_cd,
        "msg1": msg1,
        "error_message": msg1,
        "status": next_status.value,
        "updated_at": func.now(),
    }
    if broker_org_no is not None:
        values_to_update["broker_org_no"] = broker_org_no
    if broker_order_no is not None:
        values_to_update["broker_order_no"] = broker_order_no
    if request_payload is not None:
        values_to_update["request_payload"] = request_payload
    if response_payload is not None:
        values_to_update["submit_response_payload"] = response_payload
        
    stmt = (
        update(Order)
        .where(Order.id == order_id)
        .values(**values_to_update)
    )
    result = await db.execute(stmt)
    return result.rowcount > 0


# ⚙️ 자식 주문(정정/취소) 처리 결과를 반영하여 원주문(parent) 상태 업데이트
async def update_parent_order_after_child(
    db: AsyncSession,
    order_id: UUID,
    filled_qty: int,
    remaining_qty: int,
    next_status: ORDER_STATUS,
) -> bool:
    """
    원주문(parent) 갱신 전용 함수
    - child(cancel/modify) 주문의 처리 결과를 반영하여 원주문의 remaining_qty, status, updated_at 만 갱신한다.
    - 원주문의 broker 응답 원문, rt_cd/msg_cd/msg1, filled_qty 등은 건드리지 않는다.
    """
    stmt = (
        update(Order)
        .where(Order.id == order_id)
        .values(
            filled_qty=filled_qty,
            remaining_qty=remaining_qty,
            status=next_status.value,
            updated_at=func.now(),
        )
    )
    result = await db.execute(stmt)
    return result.rowcount > 0


async def exists_child_orders(db: AsyncSession, parent_order_id: UUID) -> bool:
    """
    특정 주문의 자식 주문 존재 여부 조회
    - parent_order_id에 해당하는 주문을 원주문으로 하는 자식 주문이 존재하는지 여부 반환
    """
    stmt = (
        select(Order.id)
        .where(Order.original_order_id == parent_order_id)
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def get_recoverable_tracking_orders(db: AsyncSession) -> Sequence[Order]:
    """
    재기동 시 worker-2 복구 대상 주문 조회
    - 상태 추적이 필요한 미종결 주문만 조회(REQUESTED, ACCEPTED, PARTIAL_FILLED)
    - 브로커 주문번호가 있는 주문만 조회(이미 브로커에 주문이 접수된 주문만 복구 대상)
    - 오래된 주문부터(created_at ASC) 순차 복구
    """
    stmt = (
        select(Order)
        .where(
            Order.status.in_([
                ORDER_STATUS.REQUESTED.value,
                ORDER_STATUS.ACCEPTED.value,
                ORDER_STATUS.PARTIAL_FILLED.value,
            ]),
            Order.broker_order_no.is_not(None),
        )
        .order_by(Order.created_at.asc())
    )

    result = await db.execute(stmt)
    return result.scalars().all()


async def get_recoverable_submit_orders(db: AsyncSession) -> Sequence[Order]:
    """
    재기동 시 worker-1 복구 대상 주문 조회
    - 아직 브로커 제출 전으로 간주할 수 있는 PENDING만 대상
    - TODO : PROCESSING 상태는 애매한 상태이므로(API에서 터진건지, 서버에서 터진건지) 일단은 복구 대상에서 제외. 필요하면 PROCESSING 상태 중에서도 브로커 제출 전으로 간주할 수 있는 주문을 선별하는 로직 추가 고려
    - 오래된 주문부터 순차 복구
    """
    stmt = (
        select(Order)
        .where(Order.status == ORDER_STATUS.PENDING.value)
        .order_by(Order.created_at.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()