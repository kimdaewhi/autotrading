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


⭐ 사용 예시
    fscore_1 = FScore()

    fscore_2 = FScore(
        threshold=7,
        metric_weights={
            "f_roa": 1.5,
            "f_cfo": 1.5,
            "f_delta_roa": 1.2,
            "f_accrual": 1.2,
        }
    )

    fscore_3 = FScore(
        enabled_categories={"P", "F"},  # 수익성 및 재무 성과 지표만 활성화
        threshold=3,
    )
    
"""

import pandas as pd
from typing import Callable

from app.core.enums import REPORT_CODE
from app.market.provider.dart_provider import DartProvider
from app.strategy.screener.base_screener import BaseScreener
from app.strategy.universe.universe_filters import apply_base_filters, top_by_marcap
from app.utils.logger import get_logger

logger = get_logger(__name__)

class FScore(BaseScreener):
    # 유니버스 선정을 외부에서 주입받을 수 있도록
    UniverseBuilder = Callable[[], pd.DataFrame]
    
    # 각 지표별 메타정보
    DEFAULT_METRICS = {
        "f_roa": {"category": "P", "weight": 1.0},
        "f_cfo": {"category": "P", "weight": 1.0},
        "f_delta_roa": {"category": "P", "weight": 1.0},
        "f_accrual": {"category": "P", "weight": 1.0},
        "f_delta_lever": {"category": "F", "weight": 1.0},
        "f_delta_liquid": {"category": "F", "weight": 1.0},
        "f_eq_offer": {"category": "F", "weight": 1.0},
        "f_delta_margin": {"category": "O", "weight": 1.0},
        "f_delta_turnover": {"category": "O", "weight": 1.0},
    }
    
    
    def __init__(
        self, 
        threshold: int = 7, 
        universe_builder: UniverseBuilder | None = None,
        enabled_categories: set[str] | None = None,
        metric_weights: dict[str, float] | None = None,
    ):
        """
        threshold : F-Score 필터링 기준점 (예: 7점 이상)
        universe_builder : 유니버스 빌더 함수 (ex: 시가총액 상위 200개)
        """
        self.dart_provider = DartProvider()
        self.threshold = threshold
        # 유니버스 빌더가 주어지지 않으면 기본값으로 시가총액 상위 200개 종목을 사용
        self.universe_builder = universe_builder or (lambda: top_by_marcap(n=200))
        
        # 각 지표별 가중치 설정 (기본값: 모두 1.0)
        self.enabled_categories = enabled_categories or {"P", "F", "O"}
        
        # 지표별 메타정보 복사 및 가중치 적용
        self.metric_config = {
            name: meta.copy() for name, meta in self.DEFAULT_METRICS.items()
        }
        
        # 카테고리 필터링: enabled_categories에 포함된 카테고리의 지표만 활성화
        if metric_weights:
            for metric_name, weight in metric_weights.items():
                if metric_name in self.metric_config:
                    self.metric_config[metric_name]["weight"] = weight
    
    
    # ⚙️ 지표 활성화 여부 확인 함수
    def _is_metric_enabled(self, metric_name: str) -> bool:
        category = self.metric_config[metric_name]["category"]
        return category in self.enabled_categories
    
    # ⚙️ 지표 가중치 조회 함수
    def _get_metric_weight(self, metric_name: str) -> float:
        return float(self.metric_config[metric_name]["weight"])
    
    
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
        # BS (재무상태표 : 총자산, 총부채, 유동자산, 유동부채, 자본총계, 자본금)
        total_assets_cur      = self._get_amount(df_fs, "BS", TOTAL_ASSETS, "thstrm")   # 당기 총자산
        total_assets_prev     = self._get_amount(df_fs, "BS", TOTAL_ASSETS, "frmtrm")   # 전기 총자산
        total_liab_cur        = self._get_amount(df_fs, "BS", TOTAL_LIAB, "thstrm")     # 당기 총부채
        total_liab_prev       = self._get_amount(df_fs, "BS", TOTAL_LIAB, "frmtrm")     # 전기 총부채
        current_assets_cur    = self._get_amount(df_fs, "BS", CURRENT_ASSETS, "thstrm") # 당기 유동자산
        current_assets_prev   = self._get_amount(df_fs, "BS", CURRENT_ASSETS, "frmtrm") # 전기 유동자산
        current_liab_cur      = self._get_amount(df_fs, "BS", CURRENT_LIAB, "thstrm")   # 당기 유동부채
        current_liab_prev     = self._get_amount(df_fs, "BS", CURRENT_LIAB, "frmtrm")   # 전기 유동부채
        equity_cur            = self._get_amount(df_fs, "BS", EQUITY, "thstrm")         # 당기 자본총계
        equity_prev           = self._get_amount(df_fs, "BS", EQUITY, "frmtrm")         # 전기 자본총계
        capital_stock_cur     = self._get_amount(df_fs, "BS", CAPITAL_STOCK, "thstrm")  # 당기 자본금
        capital_stock_prev    = self._get_amount(df_fs, "BS", CAPITAL_STOCK, "frmtrm")  # 전기 자본금
        
        # IS (손익계산서 : 순이익, 매출, 매출총이익)
        net_income_cur    = self._get_amount(df_fs, "IS", NET_INCOME, "thstrm")   # 당기 순이익
        net_income_prev   = self._get_amount(df_fs, "IS", NET_INCOME, "frmtrm")   # 전기 순이익
        revenue_cur       = self._get_amount(df_fs, "IS", REVENUE, "thstrm")      # 당기 매출
        revenue_prev      = self._get_amount(df_fs, "IS", REVENUE, "frmtrm")      # 전기 매출
        gross_profit_cur  = self._get_amount(df_fs, "IS", GROSS_PROFIT, "thstrm") # 당기 매출총이익
        gross_profit_prev = self._get_amount(df_fs, "IS", GROSS_PROFIT, "frmtrm") # 전기 매출총이익
        
        # CF (현금흐름표 : 영업활동현금흐름)
        cfo_cur = self._get_amount(df_fs, "CF", CFO, "thstrm")   # 당기 영업활동현금흐름
        
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
        roa_cur = net_income_cur / total_assets_cur         # ROA (총자산이익률)
        roa_prev = net_income_prev / total_assets_prev      # ROA (전기)
        
        cfo_ratio = cfo_cur / total_assets_cur              # CFO / 총자산 비율 (영업활동현금흐름이 자산 대비 얼마나 창출되었는지 평가)
        
        leverage_cur = total_liab_cur / equity_cur if equity_cur else 0      # 부채비율 (레버리지) - 부채가 자본에 비해 얼마나 많은지 평가
        leverage_prev = total_liab_prev / equity_prev if equity_prev else 0  # 부채비율 (전기)
        
        # 유동비율 (Current Ratio) - 유동자산이 유동부채를 얼마나 커버하는지 평가
        current_ratio_cur = (
            current_assets_cur / current_liab_cur if current_liab_cur else 0
        )
        # 전기 유동비율
        current_ratio_prev = (
            current_assets_prev / current_liab_prev if current_liab_prev else 0
        )
        
        # 매출총이익률 (Gross Margin) - 매출에서 매출원가를 뺀 이익이 매출에서 차지하는 비율로, 수익성 평가에 활용
        gross_margin_cur = (
            gross_profit_cur / revenue_cur
            if (gross_profit_cur is not None and revenue_cur is not None and revenue_cur != 0)
            else 0
        )
        # 전기 매출총이익률
        gross_margin_prev = (
            gross_profit_prev / revenue_prev
            if (gross_profit_prev is not None and revenue_prev is not None and revenue_prev != 0)
            else 0
        )
        
        # 자산회전율 (Asset Turnover) - 자산이 매출을 창출하는 효율성을 평가하는 지표로, 매출을 총자산으로 나누어 계산
        turnover_cur = (
            revenue_cur / total_assets_cur
            if (revenue_cur is not None and total_assets_cur != 0)
            else 0
        )
        # 전기 자산회전율
        turnover_prev = (
            revenue_prev / total_assets_prev
            if (revenue_prev is not None and total_assets_prev != 0)
            else 0
        )
        
        # ── 원점수(0/1) 산출 ──
        raw_scores = {
            "f_roa": 1 if roa_cur > 0 else 0,                         # P
            "f_cfo": 1 if cfo_cur > 0 else 0,                         # P
            "f_delta_roa": 1 if roa_cur > roa_prev else 0,            # P
            "f_accrual": 1 if cfo_ratio > roa_cur else 0,             # P
            "f_delta_lever": 1 if leverage_cur < leverage_prev else 0,   # F
            "f_delta_liquid": 1 if current_ratio_cur > current_ratio_prev else 0,  # F
            "f_eq_offer": 1 if capital_stock_cur <= capital_stock_prev else 0,      # F
            "f_delta_margin": 1 if gross_margin_cur > gross_margin_prev else 0,      # O
            "f_delta_turnover": 1 if turnover_cur > turnover_prev else 0,            # O
        }
        
        # ── 사용 지표만 반영하여 가중 합산 ──
        weighted_scores = {}
        for metric_name, raw_value in raw_scores.items():
            if self._is_metric_enabled(metric_name):
                weighted_scores[metric_name] = raw_value * self._get_metric_weight(metric_name)
            else:
                weighted_scores[metric_name] = 0.0
        
        # 최종 F-Score는 활성화된 지표들의 가중 점수 합산
        fscore = sum(weighted_scores.values())
        
        result = {
            "code": code,
            "fscore": fscore,
            "equity": equity_cur,  # PBR 계산용
        }
        
        # 원점수(0/1)도 같이 저장
        result.update(raw_scores)
        
        # 가중 점수도 같이 저장
        for metric_name, value in weighted_scores.items():
            result[f"{metric_name}_weighted"] = value
        
        return result    
    
    
    # ⚙️ F-Score 스크리닝 메인 함수
    async def screen(self, year: int, as_of_date: str | None = None) -> pd.DataFrame:
        """
        Parameters
        ----------
        year : 결산보고서 기준 연도
            ex) year=2024 → 2024년 12월 결산 재무제표 사용
        
        as_of_date : 이 스크리닝 결과를 "사용하기 시작하는 날짜"
                    즉, 백테스트 시작일 또는 실제 매매 진입일
                    
                    ex) year=2024, as_of_date="2025-04-01"
                        → 2024년 결산보고서가 2025-04-01 기준으로 공시됐는가? ✅ OK
                    
                    ex) year=2024, as_of_date="2025-01-01"
                        → 2024년 결산보고서는 2025-04-01 이후 공시되므로
                        2025-01-01에는 아직 모르는 정보 → ❌ lookahead bias!
                    
                    None이면 오늘 날짜 기준으로 검증 (실전 매매용)
        """
        self._validate_lookahead(year=year, as_of_date=as_of_date)
        
        # ⭐ 1. 유니버스 확보 : 외부에서 주입받은 빌더 함수로 유니버스 확보 (기본값: 시가총액 상위 200개)
        logger.info(f"F-Score Screener - [{year}] 유니버스를 확보중입니다...")
        df_universe = self.universe_builder()
        
        # 우선주, 특수종목, ETF 등 제외
        df_universe = apply_base_filters(df_universe)
        
        
        # ⭐ 2. 재무 데이터 수집(Open Dart API 활용)
        logger.info(f"[{year}] 재무 데이터 수집중...")
        universe_codes = df_universe["Code"].tolist()
        
        # # 2-1. 유니버스 종목코드 목록
        # universe_codes = df_universe["Code"].tolist()
        
        # # 2-2. DB에서 이미 적재된 종목 확인
        # cached_codes = await self.dart_provider.get_cached_stock_codes(stock_codes=universe_codes, year=year, report_code=REPORT_CODE.ANNUAL.value)
        # missing_codes = [c for c in universe_codes if c not in cached_codes]
        
        # logger.info(f"[{year}] DB 캐시: {len(cached_codes)}개 / "f"API 호출 필요: {len(missing_codes)}개")
        # financial_data = {}
        
        # # 2-3. 미적재 종목만 DART API 호출 → DB 저장
        # for code in missing_codes:
        #     name = df_universe.loc[df_universe["Code"] == code, "Name"].iloc[0]
        #     try:
        #         await self.dart_provider.fetch_and_store(
        #             stock_code=code, year=year,
        #             reprt_code=REPORT_CODE.ANNUAL.value, fs_div="CFS",
        #         )
        #     except RuntimeError:
        #         try:
        #             await self.dart_provider.fetch_and_store(
        #                 stock_code=code, year=year,
        #                 reprt_code=REPORT_CODE.ANNUAL.value, fs_div="OFS",
        #             )
        #             logger.info(f"[{code} {name}] OFS(별도재무제표)로 대체")
        #         except RuntimeError:
        #             logger.info(f"[{code} {name}] 재무제표 없음 (CFS/OFS 모두)")
        #             continue
        #         except Exception as e:
        #             logger.warning(f"[{code} {name}] DB 저장 실패: {e}")
        #             continue
        #     except Exception as e:
        #         logger.warning(f"[{code} {name}] DB 저장 실패: {e}")
        #         continue
        
        # 2-4. DB에서 전체 유니버스 재무데이터 일괄 조회
        # financial_data = await self.dart_provider.get_bulk_financial_statements(
        #     stock_codes=universe_codes, year=year,
        #     report_code=REPORT_CODE.ANNUAL.value,
        # )
        
        financial_data = await self.dart_provider.fetch_and_store_bulk(
            stock_codes=universe_codes,
            year=year,
            reprt_code=REPORT_CODE.ANNUAL.value,
        )
        
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
        
        max_possible = sum(
            self._get_metric_weight(m)
            for m in self.metric_config
            if self._is_metric_enabled(m)
        )
        logger.info(f"활성 지표 최대 점수: {max_possible}, 기준점: {self.threshold}")
        
        # ⭐ 4. 필터링
        df_result = pd.DataFrame(results)
        df_high = df_result[df_result["fscore"] >= self.threshold]
        
        # ⭐ 5. PBR 계산 (시가총액 / 자본총계)
        df_marcap = df_universe[["Code", "Name", "Marcap"]].rename(columns={"Code": "code"})
        df_high = df_high.merge(df_marcap, on="code", how="left")
        df_high["pbr"] = df_high["Marcap"] / df_high["equity"]
        
        logger.info(f"F-Score 스크리닝 완료: {len(df_high)}/{len(results)}개 종목 통과 " f"(기준: {self.threshold}점 이상)")
        
        return df_high