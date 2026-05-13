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
    Calculate exact share count using two constraints — take the tighter one:
      1. Risk rule:     shares = floor(risk_amount / risk_per_share)
      2. Position cap:  shares = floor(capital * max_position_pct / entry)

    Returns a dict with all sizing figures downstream modules need.
    Raises ValueError if entry == stop (zero risk) or shares < 1.
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
    position_pct = (position_value / capital) * 100
    actual_risk = shares * risk_per_share
    potential_gain = shares * abs(entry - stop) * (abs(entry - stop) and
                     abs(config.MIN_RISK_REWARD))  # floor estimate; analyst sets real target
    # Use analyst's actual target for potential gain — caller passes it separately
    # This field is populated by format_telegram_message

    return {
        "shares": shares,
        "position_value": round(position_value, 2),
        "position_pct": round(position_pct, 1),
        "risk_amount": round(actual_risk, 2),
        "risk_per_share": round(risk_per_share, 2),
        "shares_by_risk": shares_by_risk,
        "shares_by_cap": shares_by_cap,
        "binding_rule": "risk" if shares_by_risk <= shares_by_cap else "position_cap",
    }


# ── Telegram MarkdownV2 escaping ──────────────────────────────────────────────

# All characters that must be backslash-escaped in Telegram MarkdownV2
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
    """Format a price as an escaped MarkdownV2 string."""
    if value is None:
        return "N/A"
    return _esc(f"{value:.2f}")


def _fmt_signed(value: float) -> str:
    """Format a signed dollar change (+$X.XX or -$X.XX), escaped."""
    sign = "+" if value >= 0 else ""
    return _esc(f"{sign}${value:.2f}")


# ── Message formatting ────────────────────────────────────────────────────────

def format_telegram_message(
    analyst_result: dict,
    position: Optional[dict],
    is_paper: bool = True,
    capital: float = config.ACCOUNT_CAPITAL,
) -> str:
    """
    Build the full Telegram MarkdownV2 message for a TRADE or NO_TRADE result.
    All dynamic content is escaped; structural formatting uses raw MarkdownV2.
    """
    now = datetime.now(config.GULF_TZ)
    date_str = _esc(now.strftime("%A, %b %-d"))
    mode_str = "📋 Paper Trade" if is_paper else "💵 Live Trade"

    if analyst_result.get("decision") == "NO_TRADE":
        return _format_no_trade(analyst_result, date_str, mode_str)

    return _format_trade(analyst_result, position, date_str, mode_str, capital)


def _format_trade(
    r: dict,
    position: dict,
    date_str: str,
    mode_str: str,
    capital: float,
) -> str:
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

    shares = position["shares"]
    pos_value = position["position_value"]
    pos_pct = position["position_pct"]
    risk_amt = position["risk_amount"]
    potential_gain = shares * (target - entry)
    binding = position["binding_rule"]

    risks = r.get("key_risks") or []
    risk_lines = "\n".join(f"• {_esc(rk)}" for rk in risks) if risks else _esc("None identified")

    conf_emoji = {"HIGH": "🔥", "MEDIUM": "🟡", "LOW": "🟠"}.get(r.get("confidence", ""), "🟡")

    # Note if position cap was the binding constraint
    cap_note = ""
    if binding == "position_cap":
        cap_note = (
            f"\n_\\(Position cap applied \\— "
            f"increase ACCOUNT\\_CAPITAL for larger size\\)_"
        )

    return (
        f"🎯 *WEEKLY TRADE PICK*\n"
        f"_{date_str} · {mode_str}_\n"
        f"\n"
        f"{action_emoji} *{action} \\${sym}* — {company}\n"
        f"{'━' * 22}\n"
        f"\n"
        f"💰 Entry         \\${_fmt_price(entry)}\n"
        f"🛑 Stop Loss     \\${_fmt_price(stop)}  \\({_fmt_signed(stop_diff)}\\)\n"
        f"🎯 Target        \\${_fmt_price(target)}  \\({_fmt_signed(target_diff)}\\)\n"
        f"⚖️  R:R           1:{_esc(str(rr))}\n"
        f"\n"
        f"📊 *Position* \\(${_esc(f'{capital:,.0f}')} capital\\)\n"
        f"  Shares        {_esc(str(shares))}\n"
        f"  Value         \\${_esc(f'{pos_value:,.2f}')}  \\({_esc(str(pos_pct))}%\\)\n"
        f"  Max risk      \\${_esc(f'{risk_amt:,.2f}')}\n"
        f"  Potential     {_fmt_signed(potential_gain)}"
        f"{cap_note}\n"
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
        f"🔔 _Set alerts at entry, stop, and target before Monday open\\._"
    )


def _format_no_trade(r: dict, date_str: str, mode_str: str) -> str:
    reason = _esc(r.get("no_trade_reason") or "No qualifying setup found this week.")
    return (
        f"😴 *NO TRADE THIS WEEK*\n"
        f"_{date_str} · {mode_str}_\n"
        f"\n"
        f"Reviewed all candidates — no setup meets our minimum criteria\\.\n"
        f"\n"
        f"_Reason: {reason}_\n"
        f"\n"
        f"Capital preserved\\. See you next Sunday\\."
    )
