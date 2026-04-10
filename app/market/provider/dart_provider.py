import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from functools import lru_cache

import httpx
import pandas as pd
import requests

from app.core.enums import REPORT_CODE
from app.core.settings import settings
from app.db.models.dart_financial_statement import DartFinancialStatement
from app.db.session import AsyncSessionLocal
from app.repository.dart_financial_statement_repository import bulk_insert_financial_statements, find_by_stock_codes, find_existing_stock_codes
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
    
    
    # ⚙️ 캐시된 corp_code 조회 (여러 종목)
    async def get_cached_stock_codes(
        self, stock_codes: list[str], year: int, report_code: str
    ) -> set[str]:        
        async with AsyncSessionLocal() as db:
            return await find_by_stock_codes(db, stock_codes, year, report_code)
    
    
    # ⚙️ DB에 적재된 종목코드 조회
    async def get_cached_stock_codes(
        self, stock_codes: list[str], year: int, report_code: str
    ) -> set[str]:        
        async with AsyncSessionLocal() as db:
            return await find_existing_stock_codes(db, stock_codes, str(year), report_code)
    
    
    # ⚙️ DART API에서 재무제표 조회 → DB 저장
    async def fetch_and_store(self, stock_code: str, year: int, reprt_code: str, fs_div: str) -> pd.DataFrame:
        df = await self.get_financial_statements(stock_code=stock_code, year=year, report_code=reprt_code, fs_div=fs_div)
        
        df["stock_code"] = stock_code
        
        async with AsyncSessionLocal() as db:
            await bulk_insert_financial_statements(db, df)
            await db.commit()
        
        return df
    
    
    # ⚙️ 여러 종목의 재무제표 DB 일괄 조회
    async def get_bulk_financial_statements(
        self, stock_codes: list[str], year: int, report_code: str
    ) -> dict[str, pd.DataFrame]:
        async with AsyncSessionLocal() as db:
            rows = await find_by_stock_codes(db, stock_codes, str(year), report_code)
            
        if not rows:
            return {}
        
        records = [{c.key: getattr(r, c.key) for c in DartFinancialStatement.__table__.columns} for r in rows]
        df = pd.DataFrame(records)
        
        return {code: group for code, group in df.groupby("stock_code")}
    
    
    
    # ⚙️ 종목 재무제표 조회
    async def get_financial_statements(
        self,
        stock_code: str,
        year: int,
        report_code: str = REPORT_CODE.ANNUAL.value,
        fs_div: str = "CFS",
    ) -> pd.DataFrame:
        """
        DART 단일회사 전체 재무제표 조회 (재무상태표 + 손익계산서 + 현금흐름표)

        Parameters
        ----------
        stock_code : 종목코드 6자리 (ex. "005930")
        year : 사업연도 (ex. 2024)
        report_code : REPORT_CODE enum value (ex. "11011")
        fs_div : "CFS"(연결) | "OFS"(별도)

        Returns
        -------
        pd.DataFrame
            BS + IS + CF 전체 계정과목
        """
        corp_code = self._get_corp_code(stock_code)
        
        frames = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            for sj_div in ("BS", "IS", "CF", "CIS"):
                resp = await client.get(
                    self.BASE_URL,
                    params={
                        "crtfc_key": self.api_key,
                        "corp_code": corp_code,
                        "bsns_year": str(year),
                        "reprt_code": report_code,
                        "fs_div": fs_div,
                        "sj_div": sj_div,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                
                if data.get("status") != "000":
                    continue
                
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