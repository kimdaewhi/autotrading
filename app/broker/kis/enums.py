from enum import StrEnum, Enum

# =============================== 거래 유형 식별자 ============================== #
class TRID(Enum):
    """
    [거래식별자(tr_id)]
    - Header 필드
    - 주문, 잔고 조회 등 거래 유형 구분 식별자
    """
    DOMESTIC_STOCK_BUY = ("TTTC0012U", "VTTC0012U")
    DOMESTIC_STOCK_SELL = ("TTTC0011U", "VTTC0011U")
    
    DOMESTIC_STOCK_MODIFY = ("TTTC0013U", "VTTC0013U")  # 주문 정정
    
    # 주식일별 주문 체결 조회
    DAILY_CCDL_RECENT = ("TTTC0081R", "VTTC0081R")
    DAILY_CCDL_OLD = ("CTSC9215R", "VTSC9215R")
    
    # 주식잔고 조회(국내주식)
    DOMESTIC_STOCK_BALANCE = ("TTTC8434R", "VTTC8434R")

    def resolve(self, is_paper: bool) -> str:
        return self.value[1] if is_paper else self.value[0]


class SLL_TYPE(StrEnum):
    """
    [매도유형(SLL_TYPE)]
    - Body 필드
    - 매도 주문 시 매도 유형 구분 식별자
    - 미입력시 01(일반 매도)로 간주
    """
    NORMAL = "01"        # 일반 매도
    ARBITRARY = "02"     # 임의 매도
    LOAN = "03"          # 대차 매도


class ORD_DVSN_KRX(StrEnum):
    """
    [주문구분(ORD_DVSN)] - KRX
    """
    LIMIT = "00"                    # 지정가
    MARKET = "01"                   # 시장가
    CONDITIONAL_LIMIT = "02"        # 조건부지정가
    BEST_LIMIT = "03"               # 최유리지정가
    PRIORITY_LIMIT = "04"           # 최우선지정가
    PRE_MARKET = "05"               # 장전 시간외
    AFTER_MARKET = "06"             # 장후 시간외
    SINGLE_PRICE_AFTER_HOURS = "07" # 시간외 단일가

    IOC_LIMIT = "11"                # IOC지정가
    FOK_LIMIT = "12"                # FOK지정가
    IOC_MARKET = "13"               # IOC시장가
    FOK_MARKET = "14"               # FOK시장가
    IOC_BEST = "15"                 # IOC최유리
    FOK_BEST = "16"                 # FOK최유리

    MID_PRICE = "21"                # 중간가
    STOP_LIMIT = "22"               # 스톱지정가
    MID_PRICE_IOC = "23"            # 중간가IOC
    MID_PRICE_FOK = "24"            # 중간가FOK


class ORD_DVSN_NXT(StrEnum):
    """
    [주문구분(ORD_DVSN)] - NXT
    - Body 필드
    """
    LIMIT = "00"              # 지정가
    BEST_LIMIT = "03"         # 최유리지정가
    PRIORITY_LIMIT = "04"     # 최우선지정가

    IOC_LIMIT = "11"          # IOC지정가
    FOK_LIMIT = "12"          # FOK지정가
    IOC_MARKET = "13"         # IOC시장가
    FOK_MARKET = "14"         # FOK시장가
    IOC_BEST = "15"           # IOC최유리
    FOK_BEST = "16"           # FOK최유리

    MID_PRICE = "21"          # 중간가
    STOP_LIMIT = "22"         # 스톱지정가
    MID_PRICE_IOC = "23"      # 중간가IOC
    MID_PRICE_FOK = "24"      # 중간가FOK


class ORD_DVSN_SOR(StrEnum):
    """
    [주문구분(ORD_DVSN)] - SOR
    - Body 필드
    """
    LIMIT = "00"              # 지정가
    MARKET = "01"             # 시장가
    BEST_LIMIT = "03"         # 최유리지정가
    PRIORITY_LIMIT = "04"     # 최우선지정가

    IOC_LIMIT = "11"          # IOC지정가
    FOK_LIMIT = "12"          # FOK지정가
    IOC_MARKET = "13"         # IOC시장가
    FOK_MARKET = "14"         # FOK시장가
    IOC_BEST = "15"           # IOC최유리
    FOK_BEST = "16"           # FOK최유리


class EXCG_ID_DVSN_CD(StrEnum):
    """
    [거래소구분(EXCH_DVSN)]
    - Body 필드
    - 거래소 구분 식별자
    """
    KRX = "KRX"  # KRX
    NXT = "NXT"  # NXT
    SOR = "SOR"  # SOR


# =============================== 주문 정정/취소 관련 식별자 ============================== #
class RVSE_CNCL_TYPE(StrEnum):
    """
    [정정구분(RVSE_CNCL_DVSN_CD)] - 정정 주문 시 사용
    - Body 필드
    """
    REVISE = "01"  # 정정
    CANCEL = "02"  # 취소


class RVSE_QTY_ALL_ORD_YN(StrEnum):
    """
    [잔량 전체 주문 여부(QTY_ALL_ORD_YN)]
    - Body 필드
    - 주문 수량 전체 주문 여부 식별자
    """
    YES = "Y"  # 전체
    NO = "N"   # 일부


class RVSE_INQR_DVSN_1(StrEnum):
    """
    [조회구분1(INQR_DVSN_1)]
    - Body 필드
    - 정정/취소 가능 주문 조회 시 조회 구분 식별자
    """
    ORDER = "0"  # 주문
    STOCK = "1"  # 종목


class RVSE_INQR_DVSN_2(StrEnum):
    """
    [조회구분2(INQR_DVSN_2)]
    - Body 필드
    - 정정/취소 가능 주문 조회 시 조회 구분 식별자
    """
    ALL = "0"  # 전체
    SELL = "1"  # 매도
    BUY = "2"   # 매수



# =============================== 주문 조회 관련 식별자 ============================== #
class SLL_BUY_DVSN_CD(StrEnum):
    """
    [매도/매수 구분(SLL_BUY_DVSN_CD)]
    - Body 필드
    - 매도/매수 구분 식별자
    """
    ALL = "00"      # 전체
    SELL = "01"     # 매도
    BUY = "02"      # 매수


class CCDL_DVSN_CD(StrEnum):
    """
    [체결구분(CCDL_DVSN_CD)]
    - Body 필드
    - 체결 구분 식별자
    """
    ALL = "00"      # 전체
    FILLED = "01"   # 체결
    UNFILLED = "02" # 미체결


class INQR_DVSN(StrEnum):
    """
    [조회구분(INQR_DVSN)]
    - Body 필드
    - 조회 구분 식별자
    """
    DESC = "00" # 역순
    ASC = "01"  # 정순

class INQR_DVSN_1(StrEnum):
    """
    [조회구분1(INQR_DVSN_1)]
    - Body 필드
    - 조회 구분 식별자 1
    """
    ALL = ""        # 전체
    ELW = "1"       # ELW
    FREE = "2"      # 프리보드(비상장 or 장외)


class INQR_DVSN_3(StrEnum):
    """
    [조회구분3(INQR_DVSN_3)]
    - Body 필드
    - 조회 구분 식별자 3
    """
    ALL = "00"          # 전체
    CASH = "01"         # 현금
    MARGIN = "02"       # 신용
    COLLATERAL = "03"   # 담보
    LOAN = "04"         # 대주
    LEND = "05"         # 대여
    OWN_FINANCING = "06" # 자기융자신규/상환
    MARKET_FINANCING = "07" # 유통융자신규/상환