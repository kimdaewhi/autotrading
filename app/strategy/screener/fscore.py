"""
⭐ F-Score Screener
    * 스크리닝을 통한 유니버스 선정 모델
    * 재무 데이터 기반의 퀄리티 스코어링
    * Piotroski F-Score를 활용하여 기업의 재무 건전성과 성장성을 평가
    * 각 지표가 우수할 경우 1점, 그렇지 않으면 0점으로 평가하여 총 9점 만점의 F-Score 산출

☑️ Scoring에 사용되는 지표 대분류
    - Profitability : 수익성
    - Financial Performance : 재무 성과
    - Operating Efficiency : 영업 효율성
    - 이하 수익성 항목은 P, 재무 성과는 F, 영업 효율성은 O로 표기
    
    * F-Score = F_ROA + F_CFO + F_ΔROA + F_ACCRUAL + F_ΔLEVER + F_ΔLIQUID + F_EQ_OFFER + F_ΔMARGIN + F_ΔTURNOVER
    * 산출 방법 설명 : 
        - (P) F_ROA : ROA가 양수이면 1점, 그렇지 않으면 0점
        - (P) F_CFO : 영업활동현금흐름이 양수이면 1점, 그렇지 않으면 0점
        - (P) F_ΔROA : ROA의 변화가 양수이면 1점, 그렇지 않으면 0점
        - (P) F_ACCRUAL : CFO/총자산이 ROA보다 크면 1점, 그렇지 않으면 0점(의미 : 이익이 실제 현금흐름에 기반한 것인지 평가)
        - (F) F_ΔLEVER : 부채비율의 변화가 음수이면 1점, 그렇지 않으면 0점
        - (F) F_ΔLIQUID : 유동비율의 변화가 양수이면 1점, 그렇지 않으면 0점
        - (F) F_EQ_OFFER : 주식 발행이 없는 경우 1점, 그렇지 않으면 0점(ex. 유상증자 등으로 인해 주식 수가 증가한 경우 0점)
        - (O) F_ΔMARGIN : 매출총이익률의 변화가 양수이면 1점, 그렇지 않으면 0점
        - (O) F_ΔTURNOVER : 자산회전율의 변화가 양수이면 1점, 그렇지 않으면 0점(의미 : 자산을 얼마나 효율적으로 활용하여 매출을 창출했는지 평가)
    
"""

import pandas as pd

from app.market.provider.dart_provider import DartProvider
from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.strategy.screener.base_screener import BaseScreener
from app.utils.logger import get_logger

logger = get_logger(__name__)

class FScore(BaseScreener):
    def __init__(self, n: int = 200, threshold: int = 7):
        """
        n : 유니버스 종목 개수
        threshold : F-Score 필터링 기준점 (예: 7점 이상)
        """
        self.fdr_provider = FDRMarketDataProvider()
        self.dart_provider = DartProvider()
        self.n = n
        self.threshold = threshold
    
    
    # ⚙️ 재무제표에서 특정 계정과목의 금액 추출 함수
    def _get_amount(
        self, df_fs: pd.DataFrame, sj_div: str, account_id: str, term: str = "thstrm"
    ) -> float | None:
        """
        재무제표에서 특정 계정과목의 금액을 추출 (account_id 기반)

        Parameters
        ----------
        df_fs : 전체 재무제표 DataFrame
        sj_div : "BS" | "IS" | "CF"
        account_id : XBRL 표준계정ID (ex. "ifrs-full_Assets")
        term : "thstrm"(당기) | "frmtrm"(전기) | "bfefrmtrm"(전전기)
        """
        col = f"{term}_amount"
        row = df_fs[(df_fs["sj_div"] == sj_div) & (df_fs["account_id"] == account_id)]
        
        # IS에서 못 찾으면 CIS에서 재시도(손익계산서 > 포괄손익계산서)
        if row.empty and sj_div == "IS":
            row = df_fs[(df_fs["sj_div"] == "CIS") & (df_fs["account_id"] == account_id)]
        
        if row.empty:
            return None
        return row.iloc[0][col]
    
    # ⚙️ F-Score 산출 함수
    def _calculate_fscore(self, code: str, df_fs: pd.DataFrame) -> dict:
        """개별 종목 F-Score 산출 (9개 지표)"""

        # ── 계정 ID 상수 ──
        TOTAL_ASSETS     = "ifrs-full_Assets"
        CURRENT_ASSETS   = "ifrs-full_CurrentAssets"
        CURRENT_LIAB     = "ifrs-full_CurrentLiabilities"
        TOTAL_LIAB       = "ifrs-full_Liabilities"
        EQUITY           = "ifrs-full_Equity"
        CAPITAL_STOCK    = "ifrs-full_IssuedCapital"
        REVENUE          = "ifrs-full_Revenue"
        GROSS_PROFIT     = "ifrs-full_GrossProfit"
        NET_INCOME       = "ifrs-full_ProfitLoss"
        CFO              = "ifrs-full_CashFlowsFromUsedInOperatingActivities"

        # ── 재무 데이터 추출 ──
        # BS (재무상태표)
        total_assets_cur      = self._get_amount(df_fs, "BS", TOTAL_ASSETS, "thstrm")
        total_assets_prev     = self._get_amount(df_fs, "BS", TOTAL_ASSETS, "frmtrm")
        total_liab_cur        = self._get_amount(df_fs, "BS", TOTAL_LIAB, "thstrm")
        total_liab_prev       = self._get_amount(df_fs, "BS", TOTAL_LIAB, "frmtrm")
        current_assets_cur    = self._get_amount(df_fs, "BS", CURRENT_ASSETS, "thstrm")
        current_assets_prev   = self._get_amount(df_fs, "BS", CURRENT_ASSETS, "frmtrm")
        current_liab_cur      = self._get_amount(df_fs, "BS", CURRENT_LIAB, "thstrm")
        current_liab_prev     = self._get_amount(df_fs, "BS", CURRENT_LIAB, "frmtrm")
        equity_cur            = self._get_amount(df_fs, "BS", EQUITY, "thstrm")
        equity_prev           = self._get_amount(df_fs, "BS", EQUITY, "frmtrm")
        capital_stock_cur     = self._get_amount(df_fs, "BS", CAPITAL_STOCK, "thstrm")
        capital_stock_prev    = self._get_amount(df_fs, "BS", CAPITAL_STOCK, "frmtrm")

        # IS (손익계산서)
        net_income_cur    = self._get_amount(df_fs, "IS", NET_INCOME, "thstrm")
        net_income_prev   = self._get_amount(df_fs, "IS", NET_INCOME, "frmtrm")
        revenue_cur       = self._get_amount(df_fs, "IS", REVENUE, "thstrm")
        revenue_prev      = self._get_amount(df_fs, "IS", REVENUE, "frmtrm")
        gross_profit_cur  = self._get_amount(df_fs, "IS", GROSS_PROFIT, "thstrm")
        gross_profit_prev = self._get_amount(df_fs, "IS", GROSS_PROFIT, "frmtrm")

        # CF (현금흐름표)
        cfo_cur = self._get_amount(df_fs, "CF", CFO, "thstrm")

        # ── 필수 데이터 검증 ──
        required = {
            "total_assets_cur": total_assets_cur,
            "total_assets_prev": total_assets_prev,
            "equity_cur": equity_cur,
            "equity_prev": equity_prev,
            "net_income_cur": net_income_cur,
            "net_income_prev": net_income_prev,
            "cfo_cur": cfo_cur,
        }
        missing = [k for k, v in required.items() if v is None]
        if missing:
            raise ValueError(f"필수 계정 누락: {missing}")

        # ── 비율 계산 ──
        roa_cur = net_income_cur / total_assets_cur
        roa_prev = net_income_prev / total_assets_prev

        cfo_ratio = cfo_cur / total_assets_cur

        leverage_cur = total_liab_cur / equity_cur if equity_cur else 0
        leverage_prev = total_liab_prev / equity_prev if equity_prev else 0

        current_ratio_cur = (
            current_assets_cur / current_liab_cur if current_liab_cur else 0
        )
        current_ratio_prev = (
            current_assets_prev / current_liab_prev if current_liab_prev else 0
        )

        gross_margin_cur = gross_profit_cur / revenue_cur if (gross_profit_cur and revenue_cur) else 0
        gross_margin_prev = gross_profit_prev / revenue_prev if (gross_profit_prev and revenue_prev) else 0

        turnover_cur = revenue_cur / total_assets_cur if revenue_cur else 0
        turnover_prev = revenue_prev / total_assets_prev if revenue_prev else 0

        # ── 9개 지표 산출 ──
        # Profitability (수익성)
        f_roa = 1 if roa_cur > 0 else 0
        f_cfo = 1 if cfo_cur > 0 else 0
        f_delta_roa = 1 if roa_cur > roa_prev else 0
        f_accrual = 1 if cfo_ratio > roa_cur else 0

        # Financial Performance (재무 성과)
        f_delta_lever = 1 if leverage_cur < leverage_prev else 0
        f_delta_liquid = 1 if current_ratio_cur > current_ratio_prev else 0
        f_eq_offer = 1 if capital_stock_cur <= capital_stock_prev else 0

        # Operating Efficiency (영업 효율성)
        f_delta_margin = 1 if gross_margin_cur > gross_margin_prev else 0
        f_delta_turnover = 1 if turnover_cur > turnover_prev else 0

        fscore = (
            f_roa + f_cfo + f_delta_roa + f_accrual
            + f_delta_lever + f_delta_liquid + f_eq_offer
            + f_delta_margin + f_delta_turnover
        )

        return {
            "code": code,
            "fscore": fscore,
            "f_roa": f_roa,
            "f_cfo": f_cfo,
            "f_delta_roa": f_delta_roa,
            "f_accrual": f_accrual,
            "f_delta_lever": f_delta_lever,
            "f_delta_liquid": f_delta_liquid,
            "f_eq_offer": f_eq_offer,
            "f_delta_margin": f_delta_margin,
            "f_delta_turnover": f_delta_turnover,
        }
    
    
    
    # ⚙️ F-Score 스크리닝 메인 함수
    def screen(self, year: int) -> list[str]:
        
        # ⭐ 1. 유니버스 확보 : 시총 기준 상위 N개 종목 구성
        # TODO: 유니버스 선정 기준 다양화 & 모듈화 필요(ex. 섹터, 지수, 테마, 산업 등)
        logger.info(f"F-Score Screener - [{year}] 유니버스를 확보중입니다...")
        df_universe = self.fdr_provider.get_top_stock_list(self.n, sort_by="Marcap", ascending=False)[["Code", "Name", "Market", "Marcap"]]
        
        # 종목코드 숫자만 (특수종목 제외)
        df_universe = df_universe[df_universe["Code"].str.match(r"^\d{6}$")]
        
        # 우선주 제외 (종목코드 끝자리가 0이 아닌 경우)
        df_universe = df_universe[df_universe["Code"].str[-1] == "0"]
        
        # ETF/ETN 등 제외 (Market이 KOSPI/KOSDAQ인 것만)
        df_universe = df_universe[df_universe["Market"].isin(["KOSPI", "KOSDAQ"])]
        logger.info(f"유니버스 확보 완료: {len(df_universe)}개 종목")
        
        
        # ⭐ 2. 재무 데이터 수집(Open Dart API 활용)
        logger.info(f"[{year}] 재무 데이터 수집중...")
        financial_data = {}
        
        for _, row in df_universe.iterrows():
            code = row["Code"]
            try:
                df_fs = self.dart_provider.get_financial_statements(
                    stock_code=code, year=year, report_type="annual", fs_div="CFS",
                )
                financial_data[code] = df_fs
            except RuntimeError:
                try:
                    # 연결재무제표(CFS) 조회 실패 시 개별재무제표(OFS)가 있는지 재시도
                    df_fs = self.dart_provider.get_financial_statements(
                        stock_code=code, year=year, report_type="annual", fs_div="OFS",
                    )
                    financial_data[code] = df_fs
                    logger.info(f"[{code} {row['Name']}] OFS(별도재무제표)로 대체")
                except Exception as e:
                    logger.warning(f"[{code} {row['Name']}] 재무 데이터 수집 실패: {e}")
                    continue
            except Exception as e:
                logger.warning(f"[{code} {row['Name']}] 재무 데이터 수집 실패: {e}")
                continue
        
        logger.info(f"재무 데이터 수집 완료: {len(financial_data)}/{len(df_universe)}개 종목")
        
        # ⭐ 3. F-Score 산출
        results = []
        for code, df_fs in financial_data.items():
            try:
                score = self._calculate_fscore(code, df_fs)
                results.append(score)
            except Exception as e:
                logger.warning(f"[{code}] F-Score 산출 실패: {e}")
                continue
        
        # ⭐ 4. 필터링
        df_result = pd.DataFrame(results)
        df_high = df_result[df_result["fscore"] >= self.threshold]
        
        logger.info(f"F-Score 스크리닝 완료: {len(df_high)}/{len(results)}개 종목 통과 " f"(기준: {self.threshold}점 이상)")
        
        return df_high["code"].tolist()