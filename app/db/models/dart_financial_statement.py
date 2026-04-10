from __future__ import annotations

from sqlalchemy import BigInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class DartFinancialStatement(Base):
    __tablename__ = "dart_financial_statement"

    # PK (복합)
    rcept_no: Mapped[str] = mapped_column(String(20), primary_key=True)
    sj_div: Mapped[str] = mapped_column(String(8), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(512), primary_key=True)

    # 보고서 식별
    reprt_code: Mapped[str] = mapped_column(String(5), nullable=False)
    bsns_year: Mapped[str] = mapped_column(String(4), nullable=False)
    stock_code: Mapped[str] = mapped_column(String(6), nullable=False)
    corp_code: Mapped[str] = mapped_column(String(8), nullable=False)

    # 계정 식별
    sj_nm: Mapped[str] = mapped_column(String(64), nullable=False)
    account_nm: Mapped[str] = mapped_column(String(128), nullable=False)
    account_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 당기
    thstrm_nm: Mapped[str | None] = mapped_column(String(16), nullable=True)
    thstrm_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # 전기
    frmtrm_nm: Mapped[str | None] = mapped_column(String(16), nullable=True)
    frmtrm_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # 전전기
    bfefrmtrm_nm: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bfefrmtrm_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # 메타
    ord: Mapped[str | None] = mapped_column(String(8), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    thstrm_add_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)