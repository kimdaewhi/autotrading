from datetime import datetime
from sqlalchemy import String, DateTime, PrimaryKeyConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.models.base import Base  # 기존 경로에 맞게


class DartUnavailable(Base):
    """DART 재무제표 조회 불가 종목 네거티브 캐시"""
    __tablename__ = "dart_unavailable"
    
    stock_code: Mapped[str] = mapped_column(String(6), nullable=False)
    bsns_year: Mapped[str] = mapped_column(String(4), nullable=False)
    reprt_code: Mapped[str] = mapped_column(String(5), nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    __table_args__ = (
        PrimaryKeyConstraint("stock_code", "bsns_year", "reprt_code"),
        Index("idx_dart_unavailable_reason", "reason"),
    )
    
    def __repr__(self):
        return (
            f"<DartUnavailable("
            f"stock_code={self.stock_code}, "
            f"bsns_year={self.bsns_year}, "
            f"reprt_code={self.reprt_code}, "
            f"reason={self.reason})>"
        )