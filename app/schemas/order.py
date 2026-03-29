from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class OrderRead(BaseModel):
    id: uuid.UUID

    account_no: str
    account_product_code: str

    market: str
    stock_code: str

    order_pos: str
    order_kind: str
    order_type: str
    order_price: Decimal | None
    order_qty: int

    status: str

    requested_at: datetime
    submitted_at: datetime | None

    original_order_id: uuid.UUID | None
    original_broker_order_no: str | None
    original_broker_org_no: str | None

    broker_order_no: str | None
    broker_org_no: str | None

    rt_cd: str | None
    msg_cd: str | None
    msg1: str | None

    filled_qty: int
    remaining_qty: int
    avg_fill_price: Decimal | None

    request_payload: dict[str, Any] | None
    submit_response_payload: dict[str, Any] | None

    error_message: str | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
    
    
    @field_validator("request_payload", "submit_response_payload", mode="before")
    @classmethod
    def parse_json_fields(cls, value):
        if value is None:
            return None

        if isinstance(value, dict):
            return value

        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return None

        return value