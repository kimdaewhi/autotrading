from __future__ import annotations

from decimal import Decimal
from typing import Any


def _decimal_to_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


def serialize_order_ws_payload(order: Any) -> dict[str, Any]:
    return {
        "id": str(order.id),
        "account_no": order.account_no,
        "account_product_code": order.account_product_code,
        "market": order.market,
        "stock_code": order.stock_code,
        "order_pos": order.order_pos,
        "order_kind": order.order_kind,
        "order_type": order.order_type,
        "order_price": _decimal_to_str(order.order_price),
        "order_qty": order.order_qty,
        "status": order.status,
        "requested_at": order.requested_at.isoformat() if order.requested_at else None,
        "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
        "original_order_id": str(order.original_order_id) if order.original_order_id else None,
        "original_broker_order_no": order.original_broker_order_no,
        "original_broker_org_no": order.original_broker_org_no,
        "broker_order_no": order.broker_order_no,
        "broker_org_no": order.broker_org_no,
        "rt_cd": order.rt_cd,
        "msg_cd": order.msg_cd,
        "msg1": order.msg1,
        "filled_qty": order.filled_qty,
        "remaining_qty": order.remaining_qty,
        "avg_fill_price": _decimal_to_str(order.avg_fill_price),
        "error_message": order.error_message,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
    }