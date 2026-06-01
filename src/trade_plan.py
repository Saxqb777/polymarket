import math
import logging
from datetime import datetime
from typing import Optional

import config

logger = logging.getLogger(__name__)


# ── Position sizing ───────────────────────────────────────────────────────────

def calculate_position_size(
    entry: float,
    stop: float,
    capital: float = config.ACCOUNT_CAPITAL,
    risk_pct: float = config.RISK_PER_TRADE_PCT,
    max_position_pct: float = config.MAX_POSITION_SIZE_PCT,
) -> dict:
    """
    Calculate exact integer share count using two constraints — tighter wins:
      1. Risk rule:     shares = floor(risk_amount / risk_per_share)
      2. Position cap:  shares = floor(capital * max_position_pct / entry)

    Raises ValueError if entry == stop (zero risk) or shares < 1.
    Used for DB logging. For display use suggest_position() instead.
    """
    risk_per_share = abs(entry - stop)
    if risk_per_share == 0:
        raise ValueError("entry and stop_loss are identical — cannot size position")

    risk_amount = capital * risk_pct
    shares_by_risk = math.floor(risk_amount / risk_per_share)
    shares_by_cap = math.floor((capital * max_position_pct) / entry)
    shares = min(shares_by_risk, shares_by_cap)

    if shares < 1:
        raise ValueError(
            f"Position sizing yields 0 shares "
            f"(entry=${entry:.2f}, capital=${capital:.0f}, "
            f"max_position=${capital * max_position_pct:.0f}). "
            f"Consider increasing ACCOUNT_CAPITAL in your .env."
        )

    position_value = shares * entry
    return {
        "shares": shares,
        "position_value": round(position_value, 2),
        "position_pct": round((position_value / capital) * 100, 1),
        "risk_amount": round(shares * risk_per_share, 2),
        "risk_per_share": round(risk_per_share, 2),
        "shares_by_risk": shares_by_risk,
        "shares_by_cap": shares_by_cap,
        "binding_rule": "risk" if shares_by_risk <= shares_by_cap else "position_cap",
    }


def suggest_position(
    entry: float,
    stop: float,
    capital: float = config.ACCOUNT_CAPITAL,
    risk_pct: float = config.RISK_PER_TRADE_PCT,
    max_position_pct: float = config.MAX_POSITION_SIZE_PCT,
) -> dict:
    """
    Compute a position suggestion for display — uses fractional shares, never raises.
    Takes the tighter of the 1% risk rule and the 5% position cap.
    """
    risk_per_share = abs(entry - stop)
    risk_amount = round(capital * risk_pct, 2)
    max_position = round(capital * max_position_pct, 2)

    if risk_per_share > 0:
        shares_by_risk = risk_amount / risk_per_share
        shares_by_cap = max_position / entry if entry > 0 else 0
        suggested_shares = min(shares_by_risk, shares_by_cap)
    else:
        suggested_shares = 0.0

    suggested_value = round(suggested_shares * entry, 2)

    return {
        "suggested_shares": round(suggested_shares, 4),
        "suggested_value": suggested_value,
        "risk_amount": risk_amount,
        "max_position": max_position,
    }


# ── Telegram MarkdownV2 escaping ──────────────────────────────────────────────

_MD2_SPECIAL = r'\_*[]()~`>#+-=|{}.!'


def _esc(text: str) -> str:
    """Escape a string for Telegram MarkdownV2."""
    result = []
    for ch in str(text):
        if ch in _MD2_SPECIAL:
            result.append(f"\\{ch}")
        else:
            result.append(ch)
    return "".join(result)


def _fmt_price(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return _esc(f"{value:.2f}")


def _fmt_signed(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return _esc(f"{sign}${value:.2f}")


# ── Message formatting ────────────────────────────────────────────────────────

def format_telegram_message(
    analyst_result: dict,
    is_paper: bool = config.PAPER_TRADING,
    capital: float = config.ACCOUNT_CAPITAL,
) -> str:
    """
    Build the full Telegram MarkdownV2 message for a TRADE or NO_TRADE result.
    Position sizing is shown as a recommendation only — user sets actual size.
    """
    now = datetime.now(config.GULF_TZ)
    date_str = _esc(now.strftime("%A, %b %-d"))
    mode_str = "📋 Paper Trade" if is_paper else "💵 Live Trade"

    if analyst_result.get("decision") == "NO_TRADE":
        return _format_no_trade(analyst_result, date_str, mode_str)

    return _format_trade(analyst_result, date_str, mode_str, capital)


def _format_trade(r: dict, date_str: str, mode_str: str, capital: float) -> str:
    sym = _esc(r["symbol"])
    action = r.get("action", "BUY").upper()
    action_emoji = "📈" if action == "BUY" else "📉"
    company = _esc(config.SYMBOL_TO_COMPANY.get(r["symbol"], r["symbol"]))

    entry = r["entry_price"]
    stop = r["stop_loss"]
    target = r["target_price"]
    rr = r["risk_reward_ratio"]
    timeframe = _esc(r.get("timeframe", "5-7 days"))
    confidence = _esc(r.get("confidence", "MEDIUM"))
    rationale = _esc(r.get("rationale", ""))

    stop_diff = stop - entry
    target_diff = target - entry

    suggestion = suggest_position(entry, stop, capital)
    sug_shares = _esc(f"{suggestion['suggested_shares']:.4f}")
    sug_value = _esc(f"{suggestion['suggested_value']:.2f}")
    sug_risk = _esc(f"{suggestion['risk_amount']:.2f}")

    risks = r.get("key_risks") or []
    risk_lines = "\n".join(f"• {_esc(rk)}" for rk in risks) if risks else _esc("None identified")
    conf_emoji = {"HIGH": "🔥", "MEDIUM": "🟡", "LOW": "🟠"}.get(r.get("confidence", ""), "🟡")

    quality_tier = r.get("quality_tier", "BELOW_BAR")
    target_move_pct = r.get("target_move_pct")
    move_str = _esc(f"+{target_move_pct:.1f}%") if target_move_pct is not None else "N/A"
    tier_str = _esc(quality_tier or "BELOW_BAR")

    if quality_tier == "PREMIUM":
        header = "🌟 *PREMIUM TRADE PICK*"
        quality_block = (
            f"\n"
            f"⭐ _Premium setup \\(R:R {_esc(str(rr))}\\+, target move {move_str}\\)_\n"
            f"_Consider sizing up beyond your standard position\\._\n"
        )
    elif quality_tier == "BELOW_BAR":
        header = "📋 *BEST AVAILABLE \\(BELOW BAR\\)*"
        quality_block = (
            f"\n"
            f"⚠️ *BELOW QUALITY BAR*\n"
            f"R:R is only 1:{_esc(str(rr))} and target move is {move_str}\\.\n"
            f"The math is not strongly in your favor this week\\.\n"
            f"Trading this is your call — the bot does not recommend it\\.\n"
        )
    else:
        header = "🎯 *TRADE PICK*"
        quality_block = ""

    return (
        f"{header}\n"
        f"_{date_str} · {mode_str}_\n"
        f"{quality_block}"
        f"\n"
        f"{action_emoji} *{action} \\${sym}* — {company}\n"
        f"{'━' * 22}\n"
        f"\n"
        f"💰 Entry         \\${_fmt_price(entry)}\n"
        f"🛑 Stop Loss     \\${_fmt_price(stop)}  \\({_fmt_signed(stop_diff)}\\)\n"
        f"🎯 Target        \\${_fmt_price(target)}  \\({_fmt_signed(target_diff)}\\)\n"
        f"⚖️  R:R           1:{_esc(str(rr))}\n"
        f"📊 Target move   {move_str}   Tier: {tier_str}\n"
        f"\n"
        f"💰 *Suggested size* \\(1% risk rule\\)\n"
        f"  ≈{sug_shares} shares \\(≈\\${sug_value}\\)\n"
        f"  Max risk: ≈\\${sug_risk}\n"
        f"📌 _You set the actual size — stop and target are non\\-negotiable\\._\n"
        f"\n"
        f"⏱ Timeframe     {timeframe}\n"
        f"{conf_emoji} Confidence    {confidence}\n"
        f"\n"
        f"📝 *Why this trade*\n"
        f"{rationale}\n"
        f"\n"
        f"⚠️ *Risks*\n"
        f"{risk_lines}\n"
        f"\n"
        f"🔔 _Set alerts at entry, stop, and target before the next session open\\._"
    )


def _format_no_trade(r: dict, date_str: str, mode_str: str) -> str:
    reason = _esc(r.get("no_trade_reason") or "No qualifying setup found this run.")
    next_scan = _esc(f"Next scan {config.CADENCE_LABEL}.")
    return (
        f"😴 *NO TRADE THIS RUN*\n"
        f"_{date_str} · {mode_str}_\n"
        f"\n"
        f"Reviewed all candidates — no setup meets our minimum criteria\\.\n"
        f"\n"
        f"_Reason: {reason}_\n"
        f"\n"
        f"Capital preserved\\. {next_scan}"
    )
