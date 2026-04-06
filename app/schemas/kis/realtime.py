# app/schemas/kis/realtime.py
from __future__ import annotations
from pydantic import BaseModel


# 국내주식 실시간체결가 (H0STCNT0) 응답 필드 순서
# KIS 공식 문서 기준 46개 필드, ^ 구분자
KIS_REALTIME_PRICE_FIELDS = [
    "MKSC_SHRN_ISCD",       # 유가증권 단축 종목코드
    "STCK_CNTG_HOUR",       # 주식 체결 시간
    "STCK_PRPR",            # 주식 현재가
    "PRDY_VRSS_SIGN",       # 전일 대비 부호
    "PRDY_VRSS",            # 전일 대비
    "PRDY_CTRT",            # 전일 대비율
    "WGHN_AVRG_STCK_PRC",   # 가중 평균 주식 가격
    "STCK_OPRC",            # 주식 시가
    "STCK_HGPR",            # 주식 최고가
    "STCK_LWPR",            # 주식 최저가
    "ASKP1",                # 매도호가1
    "BIDP1",                # 매수호가1
    "CNTG_VOL",             # 체결 거래량
    "ACML_VOL",             # 누적 거래량
    "ACML_TR_PBMN",         # 누적 거래 대금
    "SELN_CNTG_CSNU",       # 매도 체결 건수
    "SHNU_CNTG_CSNU",       # 매수 체결 건수
    "NTBY_CNTG_CSNU",       # 순매수 체결 건수
    "CTTR",                 # 체결강도
    "SELN_CNTG_SMTN",       # 총 매도 수량
    "SHNU_CNTG_SMTN",       # 총 매수 수량
    "CCLD_DVSN",            # 체결구분 (1:매수, 3:장전, 5:매도)
    "SHNU_RATE",            # 매수비율
    "PRDY_VOL_VRSS_ACML_VOL_RATE",  # 전일 거래량 대비 등락율
    "OPRC_HOUR",            # 시가 시간
    "OPRC_VRSS_PRPR_SIGN",  # 시가대비구분
    "OPRC_VRSS_PRPR",       # 시가대비
    "HGPR_HOUR",            # 최고가 시간
    "HGPR_VRSS_PRPR_SIGN",  # 고가대비구분
    "HGPR_VRSS_PRPR",       # 고가대비
    "LWPR_HOUR",            # 최저가 시간
    "LWPR_VRSS_PRPR_SIGN",  # 저가대비구분
    "LWPR_VRSS_PRPR",       # 저가대비
    "BSOP_DATE",            # 영업 일자
    "NEW_MKOP_CLS_CODE",    # 신 장운영 구분 코드
    "TRHT_YN",              # 거래정지 여부
    "ASKP_RSQN1",           # 매도호가 잔량1
    "BIDP_RSQN1",           # 매수호가 잔량1
    "TOTAL_ASKP_RSQN",      # 총 매도호가 잔량
    "TOTAL_BIDP_RSQN",      # 총 매수호가 잔량
    "VOL_TNRT",             # 거래량 회전율
    "PRDY_SMNS_HOUR_ACML_VOL",      # 전일 동시간 누적 거래량
    "PRDY_SMNS_HOUR_ACML_VOL_RATE", # 전일 동시간 누적 거래량 비율
    "HOUR_CLS_CODE",        # 시간 구분 코드
    "MRKT_TRTM_CLS_CODE",   # 임의종료구분코드
    "VI_STND_PRC",          # 정적VI발동기준가
]


class KisRealtimePrice(BaseModel):
    """국내주식 실시간 체결가 (H0STCNT0) - 전체 46개 필드"""
    mksc_shrn_iscd: str             # 유가증권 단축 종목코드
    stck_cntg_hour: str             # 주식 체결 시간
    stck_prpr: str                  # 주식 현재가
    prdy_vrss_sign: str             # 전일 대비 부호
    prdy_vrss: str                  # 전일 대비
    prdy_ctrt: str                  # 전일 대비율
    wghn_avrg_stck_prc: str         # 가중 평균 주식 가격
    stck_oprc: str                  # 주식 시가
    stck_hgpr: str                  # 주식 최고가
    stck_lwpr: str                  # 주식 최저가
    askp1: str                      # 매도호가1
    bidp1: str                      # 매수호가1
    cntg_vol: str                   # 체결 거래량
    acml_vol: str                   # 누적 거래량
    acml_tr_pbmn: str               # 누적 거래 대금
    seln_cntg_csnu: str             # 매도 체결 건수
    shnu_cntg_csnu: str             # 매수 체결 건수
    ntby_cntg_csnu: str             # 순매수 체결 건수
    cttr: str                       # 체결강도
    seln_cntg_smtn: str             # 총 매도 수량
    shnu_cntg_smtn: str             # 총 매수 수량
    ccld_dvsn: str                  # 체결구분
    shnu_rate: str                  # 매수비율
    prdy_vol_vrss_acml_vol_rate: str  # 전일 거래량 대비 등락율
    oprc_hour: str                  # 시가 시간
    oprc_vrss_prpr_sign: str        # 시가대비구분
    oprc_vrss_prpr: str             # 시가대비
    hgpr_hour: str                  # 최고가 시간
    hgpr_vrss_prpr_sign: str        # 고가대비구분
    hgpr_vrss_prpr: str             # 고가대비
    lwpr_hour: str                  # 최저가 시간
    lwpr_vrss_prpr_sign: str        # 저가대비구분
    lwpr_vrss_prpr: str             # 저가대비
    bsop_date: str                  # 영업 일자
    new_mkop_cls_code: str          # 신 장운영 구분 코드
    trht_yn: str                    # 거래정지 여부
    askp_rsqn1: str                 # 매도호가 잔량1
    bidp_rsqn1: str                 # 매수호가 잔량1
    total_askp_rsqn: str            # 총 매도호가 잔량
    total_bidp_rsqn: str            # 총 매수호가 잔량
    vol_tnrt: str                   # 거래량 회전율
    prdy_smns_hour_acml_vol: str    # 전일 동시간 누적 거래량
    prdy_smns_hour_acml_vol_rate: str  # 전일 동시간 누적 거래량 비율
    hour_cls_code: str              # 시간 구분 코드
    mrkt_trtm_cls_code: str         # 임의종료구분코드
    vi_stnd_prc: str                # 정적VI발동기준가

    @classmethod
    def from_fields(cls, values: list[str]) -> KisRealtimePrice:
        field_map = dict(zip(cls.model_fields.keys(), values))
        return cls(**field_map)