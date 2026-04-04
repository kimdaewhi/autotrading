from pydantic import BaseModel, ConfigDict, Field
from typing import Optional

from app.schemas.kis.base import KISMultiOutputResponse, KISOutputResponse


# ============================== OAuth 인증 모델 ============================== #
class TokenResponse(BaseModel):
    """
    Access Token 발급 응답 모델
    """
    access_token: str = Field(..., description="접근 토큰")
    access_token_token_expired: Optional[str] = Field(None, description="토큰 만료 시간")
    token_type: str = Field(..., description="토큰 유형")
    expires_in: int = Field(..., description="만료 시간")

class ApprovalKeyResponse(BaseModel):
    """
    실시간 웹소켓 접속 승인키 발급 응답 모델
    """
    approval_key: str = Field(..., description="실시간 웹소켓 접속 승인키")


# ============================== 잔고 관련 상세 모델 ============================== #
class BalanceItem(BaseModel):
    """
    주식 잔고 조회 응답 상세 모델(1) - 종목별 잔고 정보
    """
    pdno: str = Field(..., description="종목코드(6자리)")
    prdt_name: str = Field(..., description="종목명")
    
    trad_dvsn_name: str = Field(..., description="매매 구분")
    bfdy_buy_qty: str = Field(..., description="전일 매수 수량")
    bfdy_sll_qty: str = Field(..., description="전일 매도 수량")
    thdt_buyqty: str = Field(..., description="당일 매수 수량")
    thdt_sll_qty: str = Field(..., description="당일 매도 수량")
    
    hldg_qty: str = Field(..., description="보유 수량")
    ord_psbl_qty: str = Field(..., description="주문 가능 수량")
    pchs_avg_pric: str = Field(..., description="평균 매입 단가")
    pchs_amt: str = Field(..., description="매입 금액")
    
    prpr: str = Field(..., description="현재가")
    evlu_amt: str = Field(..., description="평가 금액")
    
    evlu_pfls_amt: str = Field(..., description="평가손익 금액")
    evlu_pfls_rt: str = Field(..., description="평가 손익률")
    evlu_erng_rt: str = Field(..., description="평가 수익률(데이터 미제공; 0으로 출력)")
    
    loan_dt: str = Field(..., description="대출일자")
    loan_amt: str = Field(..., description="대출금액")
    stln_slng_chgs: str = Field(..., description="대주매각대금(공매도 금액)")
    
    expd_dt: str = Field(..., description="만기일자")
    fltt_rt: str = Field(..., description="등락율")
    bfdy_cprs_icdc: str = Field(..., description="전일대비증감")
    item_mgna_rt_name: str = Field(..., description="종목증거금 비율등급명")
    grta_rt_name: str = Field(..., description="보증금 비율등급명")
    sbst_pric: str = Field(..., description="대용가격(담보대상 종목의 가격)")
    stck_loan_unpr: str = Field(..., description="주식 대출 단가(주식 대출시 기준가)")


class BalanceSummary(BaseModel):
    """
    주식 잔고 조회 응답 상세 모델(2) - 잔고 요약 정보
    """
    dnca_tot_amt: str = Field(..., description="예수금 총액")
    nxdy_excc_amt: str = Field(..., description="익일정산금액(D+1 예수금)")
    prvs_rcdl_excc_amt: str = Field(..., description="가수도정산금액(D+2 예수금)")
    
    cma_evlu_amt: str = Field(..., description="CMA 평가 금액")
    bfdy_buy_amt: str = Field(..., description="전일 매수 금액")
    thdt_buy_amt: str = Field(..., description="당일 매수 금액")
    nxdy_auto_rdpt_amt: str = Field(..., description="익일 자동상환 금액")
    
    bfdy_sll_amt: str = Field(..., description="전일 매도 금액")
    thdt_sll_amt: str = Field(..., description="당일 매도 금액")
    d2_auto_rdpt_amt: str = Field(..., description="D+2 자동상환 금액")
    
    bfdy_tlex_amt: str = Field(..., description="전일 제비용 금액")
    thdt_tlex_amt: str = Field(..., description="당일 제비용 금액")
    
    tot_loan_amt: str = Field(..., description="총 대출 금액")
    scts_evlu_amt: str = Field(..., description="유가 평가 금액")
    tot_evlu_amt: str = Field(..., description="총 평가 금액")
    nass_amt: str = Field(..., description="순자산 금액")
    fncg_gld_auto_rdpt_yn: str = Field(..., description="융자금 자동상환 여부(Y/N)")
    
    pchs_amt_smtl_amt: str = Field(..., description="매입 금액 합계 금액")
    evlu_amt_smtl_amt: str = Field(..., description="평가 금액 합계 금액")
    evlu_pfls_smtl_amt: str = Field(..., description="평가손익 합계 금액")
    tot_stln_slng_chgs: str = Field(..., description="총 대주매각대금(총 공매도 금액)")
    bfdy_tot_asst_evlu_amt: str = Field(..., description="전일 총 자산 평가 금액")
    asst_icdc_amt: str = Field(..., description="자산 증감 금액")
    asst_icdc_erng_rt: str = Field(..., description="자산 증감 수익률(데이터 미제공)")


class BalanceResponse(BaseModel):
    """
    주식 잔고 조회 응답 모델
    """
    rt_cd: str = Field(..., description="성공 실패 여부(0: 성공, 그 외: 실패)")
    msg_cd: str = Field(..., description="응답 코드")
    msg1: str = Field(..., description="응답 메시지")
    ctx_area_fk100: str = Field(..., description="연속 조회 검색 조건 100")
    ctx_area_nk100: str = Field(..., description="연속 조회 키 100")
    output1: list[BalanceItem] = Field(..., description="응답상세1")
    output2: list[BalanceSummary] = Field(..., description="응답상세2")



# ============================== 주문 관련 모델 ============================== #
class DomesticStockOrderResult(BaseModel):
    """
    국내 주식 주문 결과 모델
    """
    KRX_FWDG_ORD_ORGNO: str = Field(..., description="계좌관리지점코드")
    ODNO: str = Field(..., description="주문번호")
    ORD_TMD: str = Field(..., description="주문시간")


class ModifiableOrderItem(BaseModel):
    """
    정정/취소 가능 주문 조회 응답 상세 모델
    """
    ord_gno_brno: str = Field(..., description="주문채번지점번호")
    odno: str = Field(..., description="주문번호")
    orgn_odno: str = Field(..., description="원주문번호")
    ord_dvsn_name: str = Field(..., description="주문구분명")
    
    pdno: str = Field(..., description="종목코드")
    prdt_name: str = Field(..., description="종목명")
    rvse_cncl_dvsn_name: str = Field(..., description="정정취소구분명")
    
    ord_qty: str = Field(..., description="주문수량")
    ord_unpr: str = Field(..., description="주문단가")
    ord_tmd: str = Field(..., description="주문시각")
    
    tot_ccld_qty: str = Field(..., description="총체결수량")
    tot_ccld_amt: str = Field(..., description="총체결금액")
    psbl_qty: str = Field(..., description="가능수량")
    
    sll_buy_dvsn_cd: str = Field(..., description="매도매수구분코드")
    ord_dvsn_cd: str = Field(..., description="주문구분코드")
    mgco_aptm_odno: str = Field(..., description="운용사지정주문번호")
    
    excg_dvsn_cd: str = Field(..., description="거래소구분코드")
    excg_id_dvsn_cd: str = Field(..., description="거래소ID구분코드")
    excg_id_dvsn_name: str = Field(..., description="거래소ID구분명")
    
    stpm_cndt_pric: str = Field(..., description="스톱지정가조건가격")
    stpm_efct_occr_yn: str = Field(..., description="스톱지정가효력발생여부")


class DailyOrderExecutionItem(BaseModel):
    """
    주식 일별 주문 체결 조회 응답 상세 모델
    """
    ord_dt: str = Field(..., description="주문일자")
    ord_gno_brno: str = Field(..., description="주문채번지점번호")
    odno: str = Field(..., description="주문번호")
    orgn_odno: str = Field(..., description="원주문번호")
    ord_dvsn_name: str = Field(..., description="주문구분명")
    sll_buy_dvsn_cd: str = Field(..., description="매도매수구분코드")
    sll_buy_dvsn_cd_name: str = Field(..., description="매도매수구분명")
    pdno: str = Field(..., description="종목코드")
    prdt_name: str = Field(..., description="종목명")
    ord_qty: str = Field(..., description="주문수량")
    ord_unpr: str = Field(..., description="주문단가")
    ord_tmd: str = Field(..., description="주문시각")
    tot_ccld_qty: str = Field(..., description="총체결수량")
    avg_prvs: str = Field(..., description="평균체결가격")
    cncl_yn: str = Field(..., description="취소여부")
    tot_ccld_amt: str = Field(..., description="총체결금액")
    loan_dt: str = Field(..., description="대출일자")
    ordr_empno: str = Field(..., description="주문자사번")
    ord_dvsn_cd: str = Field(..., description="주문구분코드")
    cncl_cfrm_qty: str = Field(..., description="취소확인수량")
    rmn_qty: str = Field(..., description="잔여수량")
    rjct_qty: str = Field(..., description="거부수량")
    ccld_cndt_name: str = Field(..., description="체결조건명")
    inqr_ip_addr: str = Field(..., description="조회IP주소")
    cpbc_ordp_ord_rcit_dvsn_cd: str = Field(..., description="주문접수구분코드")
    cpbc_ordp_infm_mthd_dvsn_cd: str = Field(..., description="주문통보방법구분코드")
    infm_tmd: str = Field(..., description="통보시각")
    ctac_tlno: str = Field(..., description="연락전화번호")
    prdt_type_cd: str = Field(..., description="상품유형코드")
    excg_dvsn_cd: str = Field(..., description="거래소구분코드")
    cpbc_ordp_mtrl_dvsn_cd: str = Field(..., description="주문매체구분코드")
    ord_orgno: str = Field(..., description="주문조직번호")
    rsvn_ord_end_dt: str = Field(..., description="예약주문종료일자")
    excg_id_dvsn_cd: str = Field(..., description="거래소ID구분코드")
    stpm_cndt_pric: str = Field(..., description="스탑조건가격")
    stpm_efct_occr_dtmd: str = Field(..., description="스탑효력발생일시")


class DailyOrderExecutionSummary(BaseModel):
    """
    주식 일별 주문 체결 조회 응답 상세 모델(2) - 일별 주문 체결 요약 정보
    """
    tot_ord_qty: str = Field(..., description="총주문수량")
    tot_ccld_qty: str = Field(..., description="총체결수량")
    tot_ccld_amt: str = Field(..., description="총체결금액")
    prsm_tlex_smtl: str = Field(..., description="추정제비용합계")
    pchs_avg_pric: str = Field(..., description="평균매입가격")

class OrderResponse(KISOutputResponse[DomesticStockOrderResult]):
    """
    국내 주식 주문 응답 모델
    """
    pass

class ModifiableOrdersResponse(KISOutputResponse[list[ModifiableOrderItem]]):
    """
    정정/취소 가능 주문 조회 응답 모델
    """
    pass


class DailyOrderExecutionResponse(KISMultiOutputResponse[list[DailyOrderExecutionItem], DailyOrderExecutionSummary]):
    """
    주식 일별 주문 체결 조회 응답 모델
    """
    pass



# ============================== 실시간 시세 관련 모델 ============================== #
class RealtimeSubscribeRequest(BaseModel):
    """
    한투 WebSocket 실시간 구독 요청 메시지
    """
    class Header(BaseModel):
        approval_key: str
        custtype: str = "P"
        tr_type: str
        content_type: str = Field("utf-8", alias="content-type")
        
        model_config = ConfigDict(populate_by_name=True)
    
    class Body(BaseModel):
        class Input(BaseModel):
            tr_id: str
            tr_key: str
            
        input: Input
    
    header: Header
    body: Body