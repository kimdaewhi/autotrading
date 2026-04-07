import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from functools import lru_cache

import pandas as pd
import requests

from app.core.settings import settings
from app.utils.logger import get_logger
from app.market.provider.base_financial_provider import BaseFinancialDataProvider


logger = get_logger(__name__)

# ──────────────────────────────────────────────
# corp_code 매핑 (모듈 레벨 캐시, 하루 1회 갱신)
# ──────────────────────────────────────────────
@lru_cache(maxsize=1)
def _load_corp_code_map(api_key: str, cache_date: date) -> dict[str, str]:
    """
    DART corpCode.xml(ZIP) → {stock_code(6자리): corp_code(8자리)}
    cache_date를 key로 사용하여 날짜가 바뀌면 자동 갱신
    """
    url = "https://opendart.fss.or.kr/api/corpCode.xml"
    resp = requests.get(url, params={"crtfc_key": api_key})
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_bytes = zf.read("CORPCODE.xml")

    root = ET.fromstring(xml_bytes)
    code_map = {}
    for corp in root.findall("list"):
        stock_code = corp.findtext("stock_code", "").strip()
        corp_code = corp.findtext("corp_code", "").strip()
        if stock_code:  # 상장법인만
            code_map[stock_code] = corp_code
    
    logger.info(f"corp_code 매핑 로드 완료: {len(code_map)}개 종목")
    return code_map


# ──────────────────────────────────────────────
# 보고서 코드 매핑
# ──────────────────────────────────────────────
REPORT_CODE = {
    "annual": "11011",      # 사업보고서
    "half": "11012",        # 반기보고서
    "q1": "11013",          # 1분기보고서
    "q3": "11014",          # 3분기보고서
}


class DartProvider(BaseFinancialDataProvider):
    BASE_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"      # 단일회사 전체 재무제표 조회

    def __init__(self, api_key: str = settings.DART_API_KEY):
        self.api_key = api_key

    # ── corp_code 조회 ──
    def _get_corp_code(self, stock_code: str) -> str:
        code_map = _load_corp_code_map(self.api_key, date.today())
        corp_code = code_map.get(stock_code)
        if corp_code is None:
            raise ValueError(f"corp_code를 찾을 수 없습니다: {stock_code}")
        return corp_code
    
    
    # ⚙️ 종목 재무제표 조회
    def get_financial_statements(
        self,
        stock_code: str,
        year: int,
        report_type: str = "annual",
        fs_div: str = "CFS",
    ) -> pd.DataFrame:
        """
        DART 단일회사 전체 재무제표 조회 (재무상태표 + 손익계산서 + 현금흐름표)

        Parameters
        ----------
        stock_code : 종목코드 6자리 (ex. "005930")
        year : 사업연도 (ex. 2024)
        report_type : "annual" | "half" | "q1" | "q3"
        fs_div : "CFS"(연결) | "OFS"(별도)

        Returns
        -------
        pd.DataFrame
            BS + IS + CF 전체 계정과목
        """
        corp_code = self._get_corp_code(stock_code)
        reprt_code = REPORT_CODE.get(report_type)
        
        if reprt_code is None:
            raise ValueError(f"잘못된 report_type: {report_type}")
        
        frames = []
        for sj_div in ("BS", "IS", "CF", "CIS"):  # 재무상태표, 손익계산서, 현금흐름표, 포괄손익계산서
            resp = requests.get(
                self.BASE_URL,
                params={
                    "crtfc_key": self.api_key,
                    "corp_code": corp_code,
                    "bsns_year": str(year),
                    "reprt_code": reprt_code,
                    "fs_div": fs_div,
                    "sj_div": sj_div,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("status") != "000":
                continue  # 해당 재무제표가 없는 경우 skip
            
            frames.append(pd.DataFrame(data["list"]))
        
        
        if not frames:
            raise RuntimeError(
                f"재무제표 데이터를 찾을 수 없습니다: {stock_code} ({year})"
            )
        
        df = pd.concat(frames, ignore_index=True)
        
        # 금액 컬럼 숫자 변환 (콤마 제거 → numeric)
        amount_cols = [
            "thstrm_amount",
            "thstrm_add_amount",
            "frmtrm_amount",
            "frmtrm_add_amount",
            "frmtrm_q_amount",
            "bfefrmtrm_amount",
        ]
        for col in amount_cols:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .str.replace(",", "", regex=False)
                    .apply(pd.to_numeric, errors="coerce")
                )
        
        return df