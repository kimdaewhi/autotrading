from enum import StrEnum, Enum

class TradingType(Enum):
    """
    [거래식별자(tr_id)]
    - Header 필드
    - 주문, 잔고 조회 등 거래 유형 구분 식별자
    """
    DOMESTIC_STOCK_BUY = ("TTTC0012U", "VTTC0012U")
    DOMESTIC_STOCK_SELL = ("TTTC0011U", "VTTC0011U")
    
    def resolve(self, is_paper: bool) -> str:
        return self.value[1] if is_paper else self.value[0]


class SellType(StrEnum):
    """
    [매도유형(SLL_TYPE)]
    - Body 필드
    - 매도 주문 시 매도 유형 구분 식별자
    - 미입력시 01(일반 매도)로 간주
    """
    NORMAL = "01"        # 일반 매도
    ARBITRARY = "02"     # 임의 매도
    LOAN = "03"          # 대차 매도


class KRXOrderDivision(StrEnum):
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


class NXTOrderDivision(StrEnum):
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


class SOROrderDivision(StrEnum):
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


class MarketType(StrEnum):
    """
    [거래소구분(EXCH_DVSN)]
    - Body 필드
    - 거래소 구분 식별자
    """
    KRX = "KRX"  # KRX
    NXT = "NXT"  # NXT
    SOR = "SOR"  # SOR