from __future__ import annotations
from unittest.mock import AsyncMock

import pytest

from app.broker.kis.kis_order import KISOrder
from app.schemas.kis import DailyOrderExecutionResponse, OrderResponse


def make_order_response(
    *,
    rt_cd: str = "0",
    msg_cd: str = "40600000",
    msg1: str = "[Mock] 모의투자 매수주문이 완료 되었습니다.",
    broker_org_no: str = "00950",
    broker_order_no: str = "0000013903",
    ord_tmd: str = "111554",
) -> OrderResponse:
    return OrderResponse(
        rt_cd=rt_cd,
        msg_cd=msg_cd,
        msg1=msg1,
        output={
            "KRX_FWDG_ORD_ORGNO": broker_org_no,
            "ODNO": broker_order_no,
            "ORD_TMD": ord_tmd,
        },
    )


def make_daily_execution_response(
    *,
    rt_cd: str = "0",
    msg_cd: str = "20310000",
    msg1: str = "[Mock] 모의투자 조회가 완료되었습니다.",
    broker_org_no: str = "00950",
    broker_order_no: str = "0000013903",
    stock_code: str = "064850",
    order_qty: str = "10",
    filled_qty: str = "10",
    unfilled_qty: str = "0",
    avg_price: str = "20000",
    canceled: bool = False,
) -> DailyOrderExecutionResponse:
    return DailyOrderExecutionResponse(
        rt_cd=rt_cd,
        msg_cd=msg_cd,
        msg1=msg1,
        ctx_area_fk100="",
        ctx_area_nk100="",
        output1=[
            {
                "ord_dt": "20260323",
                "ord_gno_brno": broker_org_no,
                "odno": broker_order_no,
                "orgn_odno": "",
                "ord_dvsn_name": "지정가",
                "sll_buy_dvsn_cd": "02",
                "sll_buy_dvsn_cd_name": "매수",
                "pdno": stock_code,
                "prdt_name": "삼성전자",
                "ord_qty": order_qty,
                "ord_unpr": avg_price,
                "ord_tmd": "120000",
                "tot_ccld_qty": filled_qty,
                "avg_prvs": avg_price,
                "cncl_yn": "Y" if canceled else "N",
                "tot_ccld_amt": str(int(filled_qty) * int(avg_price)),
                "loan_dt": "",
                "ordr_empno": "",
                "ord_dvsn_cd": "00",
                "cncl_cfrm_qty": "0",
                "rmn_qty": unfilled_qty,
                "rjct_qty": "0",
                "ccld_cndt_name": "",
                "inqr_ip_addr": "",
                "cpbc_ordp_ord_rcit_dvsn_cd": "",
                "cpbc_ordp_infm_mthd_dvsn_cd": "",
                "infm_tmd": "",
                "ctac_tlno": "",
                "prdt_type_cd": "",
                "excg_dvsn_cd": "01",
                "cpbc_ordp_mtrl_dvsn_cd": "",
                "ord_orgno": "",
                "rsvn_ord_end_dt": "",
                "excg_id_dvsn_cd": "KRX",
                "stpm_cndt_pric": "",
                "stpm_efct_occr_dtmd": "",
            }
        ],
        output2={
            "tot_ord_qty": order_qty,
            "tot_ccld_qty": filled_qty,
            "tot_ccld_amt": str(int(filled_qty) * int(avg_price)),
            "prsm_tlex_smtl": "0",
            "pchs_avg_pric": avg_price,
        }
        
    )


def install_kis_market_api_mock(
    monkeypatch: pytest.MonkeyPatch,
    *,
    buy_response: OrderResponse | None = None,
    sell_response: OrderResponse | None = None,
    daily_execution_response: DailyOrderExecutionResponse | None = None,
) -> dict[str, AsyncMock]:
    """
    장 마감 시간대 통합 테스트를 위해 실시간 주문/시세성 KIS API만 가짜 응답으로 교체한다.
    DB 세션과 토큰 발급 로직은 그대로 두고, KISOrder의 실제 HTTP 호출 함수만 monkeypatch 한다.
    """
    mocks: dict[str, AsyncMock] = {}

    if buy_response is not None:
        buy_mock = AsyncMock(return_value=buy_response)
        monkeypatch.setattr(KISOrder, "buy_domestic_stock_by_cash", buy_mock)
        mocks["buy_domestic_stock_by_cash"] = buy_mock

    if sell_response is not None:
        sell_mock = AsyncMock(return_value=sell_response)
        monkeypatch.setattr(KISOrder, "sell_domestic_stock_by_cash", sell_mock)
        mocks["sell_domestic_stock_by_cash"] = sell_mock

    if daily_execution_response is not None:
        execution_mock = AsyncMock(return_value=daily_execution_response)
        monkeypatch.setattr(KISOrder, "get_daily_order_executions", execution_mock)
        mocks["get_daily_order_executions"] = execution_mock

    return mocks