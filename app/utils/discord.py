"""
⭐ Discord Webhook 알림 유틸리티

채널별 역할:
    #rebalance : 리밸런싱 실행 결과 요약 (성공/경고/실패)
    #error     : 개별 주문 실패 알림
    #health    : 시스템 헬스체크 (Phase 1 #3에서 구현)

사용 예시:
    from app.utils.discord import send_rebalance_alert, send_order_error_alert

    # 리밸런싱 완료 후
    await send_rebalance_alert(result)

    # 주문 실패 시
    await send_order_error_alert(
        stock_code="005930",
        stock_name="삼성전자",
        order_id="abc-123",
        error_message="KIS API timeout",
    )

설계 원칙:
    - fire-and-forget: 알림 전송 실패가 본체 로직을 멈추지 않음
    - 비동기 기본, Celery 워커용 동기 래퍼 제공
    - Embed 카드로 구조화된 알림
"""

import asyncio
import traceback
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from app.core.settings import settings
from app.utils.logger import get_logger
from app.schemas.strategy.trading import RebalanceResult

logger = get_logger(__name__)


# ── Discord Embed 색상 (Decimal) ──
class EmbedColor:
    SUCCESS = 3066993     # 초록 (#2ECC71)
    WARNING = 16776960    # 노랑 (#FFFF00)
    ERROR = 15158332      # 빨강 (#E74C3C)
    INFO = 3447003        # 파랑 (#3498DB)


# ── 내부 공통: 웹훅 전송 ──
async def _send_webhook(webhook_url: str, payload: dict) -> bool:
    """
    Discord 웹훅으로 메시지 전송 (fire-and-forget)
    
    Returns
    -------
    bool : 전송 성공 여부
    """
    if not webhook_url:
        logger.warning("[discord] 웹훅 URL이 설정되지 않았습니다.")
        return False
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=payload)
            
            if response.status_code == 204:
                return True
            elif response.status_code == 429:
                retry_after = response.json().get("retry_after", "?")
                logger.warning(f"[discord] Rate limit 초과. retry_after={retry_after}s")
                return False
            else:
                logger.warning(
                    f"[discord] 웹훅 전송 실패. "
                    f"status={response.status_code}, body={response.text[:200]}"
                )
                return False
    except Exception as e:
        logger.warning(f"[discord] 웹훅 전송 중 예외 발생: {e}")
        return False


def _send_webhook_sync(webhook_url: str, payload: dict) -> bool:
    """동기 래퍼 (Celery 워커에서 사용)"""
    try:
        loop = asyncio.get_running_loop()
        asyncio.ensure_future(_send_webhook(webhook_url, payload))
        return True
    except RuntimeError:
        return asyncio.run(_send_webhook(webhook_url, payload))


def _truncate(text: str, max_len: int = 4096) -> str:
    """Discord Embed description 길이 제한"""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _pad(text: str, width: int) -> str:
    """한글 포함 문자열 고정폭 패딩 (한글=2칸, 영문/숫자=1칸)"""
    display_width = 0
    for ch in text:
        if '\uac00' <= ch <= '\ud7a3' or '\u4e00' <= ch <= '\u9fff':
            display_width += 2
        else:
            display_width += 1
    padding = max(width - display_width, 0)
    return text + " " * padding


def _format_amount(value: int) -> str:
    """금액을 만원 단위로 포맷 (100만 이상이면 만원 단위)"""
    if abs(value) >= 10000:
        return f"{value / 10000:.1f}만"
    return f"{value:,}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# #rebalance 채널 알림
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_rebalance_alert(result: RebalanceResult) -> bool:
    """리밸런싱 실행 결과를 #rebalance 채널에 Embed로 전송"""
    webhook_url = getattr(settings, "DISCORD_REBALANCE_WEBHOOK_URL", "")
    
    # ── 상태별 색상/타이틀 ──
    if not result.success and result.error_message:
        color = EmbedColor.ERROR
        title = "❌ 리밸런싱 실패"
    elif result.order_result and (
        (result.order_result.sell_fill_result and result.order_result.sell_fill_result.timed_out)
        or (result.order_result.buy_fill_result and result.order_result.buy_fill_result.timed_out)
    ):
        color = EmbedColor.WARNING
        title = "⚠️ 리밸런싱 완료 (일부 타임아웃)"
    elif result.dry_run:
        color = EmbedColor.INFO
        title = "🔍 리밸런싱 DRY RUN"
    else:
        color = EmbedColor.SUCCESS
        title = "✅ 리밸런싱 완료"
    
    # ── description 구성 (코드블록 테이블) ──
    desc_parts = []
    
    # 기본 정보 헤더
    mode = "DRY RUN" if result.dry_run else "실전"
    desc_parts.append(
        f"`{str(result.rebalance_id)[:8]}` · {mode} · "
        f"유니버스 **{result.universe_count}**종목 → 시그널 **{result.signal_buy_count}**종목"
    )
    
    # diff 결과 테이블
    if result.diff_result:
        diff = result.diff_result
        
        # 매도 테이블
        if diff.sell_list:
            desc_parts.append("")
            desc_parts.append("**🔴 매도**")
            sell_table = "```"
            sell_table += f"{'종목':<10} {'수량':>5} {'금액':>10}\n"
            sell_table += "─" * 35 + "\n"
            for item in diff.sell_list:
                name = _pad(item.stock_name, 10)
                sell_table += f"{name} {item.order_qty:>4}주 {_format_amount(item.current_value):>9}\n"
            sell_table += "─" * 35 + "\n"
            sell_table += f"{'합계':<10} {len(diff.sell_list):>4}건 {_format_amount(diff.total_sell_value):>9}\n"
            sell_table += "```"
            desc_parts.append(sell_table)
        
        # 매수 테이블
        if diff.buy_list:
            desc_parts.append("**🟢 매수**")
            buy_table = "```"
            buy_table += f"{'종목':<10} {'수량':>5} {'금액':>10}\n"
            buy_table += "─" * 35 + "\n"
            for item in diff.buy_list:
                name = _pad(item.stock_name, 10)
                buy_table += f"{name} {item.order_qty:>4}주 {_format_amount(item.target_value):>9}\n"
            buy_table += "─" * 35 + "\n"
            buy_table += f"{'합계':<10} {len(diff.buy_list):>4}건 {_format_amount(diff.total_buy_value):>9}\n"
            buy_table += "```"
            desc_parts.append(buy_table)
        
        # 유지 종목 (한 줄 요약)
        if diff.hold_list:
            hold_names = ", ".join(item.stock_name for item in diff.hold_list)
            desc_parts.append(f"**⚪ 유지** ({len(diff.hold_list)}종목): {hold_names}")
    
    description = "\n".join(desc_parts)
    
    # ── fields: 체결 현황 + 예수금 (핵심 숫자만) ──
    fields = []
    
    if result.order_result and not result.dry_run:
        order_r = result.order_result
        
        if order_r.sell_fill_result:
            sfr = order_r.sell_fill_result
            status = "⏰" if sfr.timed_out else "✅"
            fields.append({
                "name": "매도 체결",
                "value": f"{sfr.filled_orders}/{sfr.total_orders}건 {status}\n{sfr.total_filled_amount:,}원",
                "inline": True,
            })
        
        if order_r.buy_fill_result:
            bfr = order_r.buy_fill_result
            status = "⏰" if bfr.timed_out else "✅"
            fields.append({
                "name": "매수 체결",
                "value": f"{bfr.filled_orders}/{bfr.total_orders}건 {status}",
                "inline": True,
            })
    
    if result.diff_result:
        fields.append({
            "name": "예수금 변동",
            "value": f"{result.diff_result.available_cash:,}원\n→ {result.diff_result.estimated_cash_after:,}원",
            "inline": True,
        })
    
    # 에러 메시지
    if result.error_message:
        fields.append({
            "name": "❌ 오류",
            "value": f"```{result.error_message}```",
            "inline": False,
        })
    
    embed = {
        "title": title,
        "description": _truncate(description),
        "color": color,
        "fields": fields,
        "footer": {"text": f"rebalance_id: {str(result.rebalance_id)[:8]}"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    payload = {"embeds": [embed]}
    
    return await _send_webhook(webhook_url, payload)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# #error 채널 알림
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_order_error_alert(
    stock_code: str,
    stock_name: str,
    order_id: str,
    order_action: str = "",
    error_message: str = "",
    context: dict | None = None,
) -> bool:
    """주문 실패를 #error 채널에 Embed로 전송"""
    webhook_url = getattr(settings, "DISCORD_ERROR_WEBHOOK_URL", "")
    
    fields = [
        {"name": "종목", "value": f"`{stock_code}` {stock_name}", "inline": True},
        {"name": "주문", "value": order_action or "N/A", "inline": True},
        {"name": "order_id", "value": f"`{str(order_id)[:8]}`", "inline": True},
    ]
    
    if error_message:
        fields.append({
            "name": "에러 메시지",
            "value": f"```{error_message[:1000]}```",
            "inline": False,
        })
    
    if context:
        context_str = "\n".join(f"**{k}:** {v}" for k, v in context.items())
        fields.append({
            "name": "상세 정보",
            "value": context_str[:1024],
            "inline": False,
        })
    
    embed = {
        "title": "🚨 주문 실패",
        "color": EmbedColor.ERROR,
        "fields": fields,
        "footer": {"text": "Autotrading Error"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    return await _send_webhook(webhook_url, {"embeds": [embed]})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# #health 채널 알림
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_health_alert(
    title: str,
    message: str,
    is_healthy: bool = True,
) -> bool:
    """시스템 헬스체크 결과를 #health 채널에 전송"""
    webhook_url = getattr(settings, "DISCORD_HEALTH_CHECK_WEBHOOK_URL", "")
    
    embed = {
        "title": f"{'✅' if is_healthy else '🚨'} {title}",
        "description": message,
        "color": EmbedColor.SUCCESS if is_healthy else EmbedColor.ERROR,
        "footer": {"text": "Autotrading Health"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    return await _send_webhook(webhook_url, {"embeds": [embed]})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 동기 래퍼 (Celery 워커용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_order_error_alert_sync(
    stock_code: str,
    stock_name: str,
    order_id: str,
    order_action: str = "",
    error_message: str = "",
    context: dict | None = None,
) -> bool:
    """send_order_error_alert의 동기 래퍼"""
    webhook_url = getattr(settings, "DISCORD_ERROR_WEBHOOK_URL", "")
    
    fields = [
        {"name": "종목", "value": f"`{stock_code}` {stock_name}", "inline": True},
        {"name": "주문", "value": order_action or "N/A", "inline": True},
        {"name": "order_id", "value": f"`{str(order_id)[:8]}`", "inline": True},
    ]
    
    if error_message:
        fields.append({
            "name": "에러 메시지",
            "value": f"```{error_message[:1000]}```",
            "inline": False,
        })
    
    if context:
        context_str = "\n".join(f"**{k}:** {v}" for k, v in context.items())
        fields.append({
            "name": "상세 정보",
            "value": context_str[:1024],
            "inline": False,
        })
    
    embed = {
        "title": "🚨 주문 실패",
        "color": EmbedColor.ERROR,
        "fields": fields,
        "footer": {"text": "Autotrading Error"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    return _send_webhook_sync(webhook_url, {"embeds": [embed]})