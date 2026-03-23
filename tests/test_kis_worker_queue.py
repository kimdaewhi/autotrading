import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

import app.worker.tasks_order as tasks_order
import app.worker.tasks_order_status as tasks_order_status
from app.core.settings import settings
from tests.support.kis_market_api_mock import (
    install_kis_market_api_mock,
    make_daily_execution_response,
    make_order_response,
)

TEST_ORDER_ID = "773c0ebd-1591-4f72-98c7-a739d2eb5b71"


@pytest_asyncio.fixture
async def real_test_session_local(monkeypatch):
    engine = create_async_engine(
        settings.DB_URL,
        poolclass=NullPool,
    )
    session_local = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )

    monkeypatch.setattr(tasks_order, "AsyncSessionLocal", session_local)
    monkeypatch.setattr(tasks_order_status, "AsyncSessionLocal", session_local)

    yield session_local

    await engine.dispose()


@pytest.mark.asyncio
async def test_order_pipeline_submit_then_track(monkeypatch, real_test_session_local):
    monkeypatch.setattr(
        "app.worker.tasks_order.redis.from_url",
        MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        "app.worker.tasks_order_status.redis.from_url",
        MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        "app.worker.tasks_order.AuthService.get_valid_access_token",
        AsyncMock(return_value="mock-access-token"),
    )
    monkeypatch.setattr(
        "app.worker.tasks_order_status.AuthService.get_valid_access_token",
        AsyncMock(return_value="mock-access-token"),
    )
    monkeypatch.setattr(
        "app.worker.tasks_order.process_order_status.delay",
        MagicMock(),
    )

    kis_mocks = install_kis_market_api_mock(
        monkeypatch,
        buy_response=make_order_response(
            msg1="모의투자 매수주문이 완료 되었습니다.",
            broker_org_no="00950",
            broker_order_no="0000013903",
            ord_tmd="111554",
        ),
        daily_execution_response=make_daily_execution_response(
            broker_org_no="00950",
            broker_order_no="0000013903",
            order_qty="5",
            filled_qty="5",
            unfilled_qty="0",
            avg_price="70100",
        ),
    )

    await tasks_order._process_order(TEST_ORDER_ID)
    await tasks_order_status._process_order_status(TEST_ORDER_ID)

    kis_mocks["buy_domestic_stock_by_cash"].assert_awaited_once()
    kis_mocks["get_daily_order_executions"].assert_awaited_once()