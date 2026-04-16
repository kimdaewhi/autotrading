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
from app.repository.dart_financial_statement_repository import bulk_insert_financial_statements, find_by_stock_codes, find_existing_stock_codes, find_unavailable_codes, mark_unavailable_bulk
from app.utils.logger import get_logger
from app.market.provider.base_financial_provider import BaseFinancialDataProvider


logger = get_logger(__name__)

# ──────────────────────────────────────────────
# corp_code, corp_name 매핑 (모듈 레벨 캐시, 하루 1회 갱신)
# ──────────────────────────────────────────────
@lru_cache(maxsize=1)
def _load_corp_maps(api_key: str, cache_date: date) -> tuple[dict[str, str], dict[str, str]]:
    """
    DART corpCode.xml(ZIP) → (code_map, name_map)
    - code_map: {stock_code: corp_code}
    - name_map: {stock_code: corp_name}
    """
    url = "https://opendart.fss.or.kr/api/corpCode.xml"
    resp = requests.get(url, params={"crtfc_key": api_key})
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_bytes = zf.read("CORPCODE.xml")

    root = ET.fromstring(xml_bytes)
    code_map = {}
    name_map = {}
    for corp in root.findall("list"):
        stock_code = corp.findtext("stock_code", "").strip()
        corp_code = corp.findtext("corp_code", "").strip()
        corp_name = corp.findtext("corp_name", "").strip()
        if stock_code:
            code_map[stock_code] = corp_code
            name_map[stock_code] = corp_name

    logger.info(f"corp_code 매핑 로드 완료: {len(code_map)}개 종목")
    return code_map, name_map


# corp_code 매핑 조회 (stock_code → corp_code)
@lru_cache(maxsize=1)
def _load_corp_code_map(api_key: str, cache_date: date) -> dict[str, str]:
    code_map, _ = _load_corp_maps(api_key, cache_date)
    return code_map


# corp_name 매핑 조회 (stock_code → corp_name)
def _load_stock_name_map(api_key: str) -> dict[str, str]:
    _, name_map = _load_corp_maps(api_key, date.today())
    return name_map



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
    async def fetch_and_store(
        self,
        stock_code: str,
        year: int,
        reprt_code: str,
    ) -> pd.DataFrame:
        """
        단일 종목 재무제표 DART 조회 → DB 저장
        
        CFS(연결재무제표) 우선 시도, 없으면 OFS(별도재무제표)로 폴백
        둘 다 없으면 RuntimeError 발생
        """
        try:
            df = await self.get_financial_statements(
                stock_code=stock_code,
                year=year,
                report_code=reprt_code,
                fs_div="CFS",
            )
        except RuntimeError:
            # CFS 실패 → OFS 폴백
            df = await self.get_financial_statements(
                stock_code=stock_code,
                year=year,
                report_code=reprt_code,
                fs_div="OFS",
            )
            logger.info(f"[{stock_code}] OFS(별도재무제표)로 대체")
        
        df["stock_code"] = stock_code
        
        async with AsyncSessionLocal() as db:
            await bulk_insert_financial_statements(db, df)
            await db.commit()
        
        return df
    
    
    async def fetch_and_store_bulk(
        self,
        stock_codes: list[str],
        year: int,
        reprt_code: str,
    ) -> dict[str, pd.DataFrame]:
        """
        유니버스 종목의 재무제표를 일괄 조회/저장
        
        처리 순서:
        1. DB 캐시 확인 (이미 저장된 종목 제외)
        2. 네거티브 캐시 확인 (조회 불가 종목 제외)
        3. 남은 종목만 DART API 호출 (CFS → OFS 폴백은 fetch_and_store 내부에서 자동 처리)
        4. 실패 종목은 네거티브 캐시에 기록
        5. 전체 종목 재무 데이터 일괄 조회 후 반환
        """
        async with AsyncSessionLocal() as db:
            # 1. DB 캐시 확인
            cached_codes = await find_existing_stock_codes(db, stock_codes, str(year), reprt_code)
            
            # 2. 네거티브 캐시 확인
            unavailable_codes = await find_unavailable_codes(db, stock_codes, str(year), reprt_code)
            
            # 3. 실제 API 호출 대상
            missing_codes = [
                c for c in stock_codes
                if c not in cached_codes and c not in unavailable_codes
            ]
            
            logger.info(
                f"[{year}] DB 캐시: {len(cached_codes)}개 / "
                f"네거티브 캐시: {len(unavailable_codes)}개 / "
                f"API 호출 필요: {len(missing_codes)}개"
            )
            
            # 4. 미적재 종목 API 호출
            unavailable_records = []
            for code in missing_codes:
                try:
                    await self.fetch_and_store(code, year, reprt_code)
                except RuntimeError:
                    # CFS/OFS 모두 실패 → 네거티브 캐시 기록 대상
                    logger.info(f"[{code}] 재무제표 없음 (CFS/OFS 모두)")
                    unavailable_records.append({
                        "stock_code": code,
                        "bsns_year": str(year),
                        "reprt_code": reprt_code,
                        "reason": "no_data",
                    })
                except Exception as e:
                    logger.warning(f"[{code}] DB 저장 실패: {e}")
            
            # 5. 실패 종목 네거티브 캐시에 기록
            if unavailable_records:
                await mark_unavailable_bulk(db, unavailable_records)
                await db.commit()
                logger.info(f"네거티브 캐시에 {len(unavailable_records)}개 종목 기록")
        
        # 6. 전체 유니버스 재무 데이터 일괄 조회
        return await self.get_bulk_financial_statements(
            stock_codes=stock_codes,
            year=year,
            report_code=reprt_code,
        )
    
    
    
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