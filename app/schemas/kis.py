from pydantic import BaseModel, Field
from typing import Optional


# ============================== OAuth 인증 모델 ============================== #
class TokenResponse(BaseModel):
    """
    KIS Access Token
    """
    access_token: str = Field(..., description="접근 토큰")
    access_token_token_expired: Optional[str] = Field(None, description="토큰 만료 시간")
    token_type: str = Field(..., description="토큰 유형")
    expires_in: int = Field(..., description="만료 시간")

class ApprovalKeyResponse(BaseModel):
    """
    KIS 실시간 웹소켓 접속 승인키
    """
    approval_key: str = Field(..., description="실시간 웹소켓 접속 승인키")


# ============================== 잔고 관련 상세 모델 ============================== #
class BalanceItem(BaseModel):
    """
    KIS 주식 잔고 조회 응답 상세 모델(1) - 종목별 잔고 정보
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
    KIS 주식 잔고 조회 응답 상세 모델(2) - 잔고 요약 정보
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
    KIS 주식 잔고 조회 응답 모델
    """
    rt_cd: str = Field(..., description="성공 실패 여부(0: 성공, 그 외: 실패)")
    msg_cd: str = Field(..., description="응답 코드")
    msg1: str = Field(..., description="응답 메시지")
    ctx_area_fk100: str = Field(..., description="연속 조회 검색 조건 100")
    ctx_area_nk100: str = Field(..., description="연속 조회 키 100")
    output1: list[BalanceItem] = Field(..., description="응답상세1")
    output2: list[BalanceSummary] = Field(..., description="응답상세2")



# ============================== 국내주식 주문 관련 모델 ============================== #
class DomesticStockOrderResult(BaseModel):
    KRX_FWDG_ORD_ORGNO: str = Field(..., description="계좌관리지점코드")
    ODNO: str = Field(..., description="주문번호")
    ORD_TMD: str = Field(..., description="주문시간")

class DomesticStockOrderResponse(BaseModel):
    """
    KIS 주식 주문 응답 모델
    """
    rt_cd: str = Field(..., description="성공 실패 여부(0: 성공, 그 외: 실패)")
    msg_cd: str = Field(..., description="응답 코드")
    msg1: str = Field(..., description="응답 메시지")
    output: DomesticStockOrderResult = Field(None, description="응답 상세")