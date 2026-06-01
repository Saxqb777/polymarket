import json
import logging
import re
from typing import Optional

import anthropic

import config

logger = logging.getLogger(__name__)

# Cached Anthropic client
_anthropic_client: Optional[anthropic.Anthropic] = None

# ── System prompt (static — qualifies for prompt caching) ─────────────────────
# Kept verbose intentionally: more context → better trade decisions.
# Marked cache_control: ephemeral so Sonnet caches this across the session.
_ANALYST_SYSTEM_PROMPT = """You are a professional US equity swing trader with 15 years of experience. You specialise in high-probability setups with defined risk. Your job is to review a shortlist of stocks, pick the single best swing trade for the upcoming week, and produce a complete trade plan.

## Your trading style
- You trade 3–10 day swings in liquid US large/mid-cap stocks
- Preferred setups: (1) pullback entries to a rising 20-day MA in an uptrend, (2) breakouts above a clear resistance level with volume confirmation, (3) oversold RSI bounce from support in a stock with a strong fundamental catalyst
- You avoid: choppy sideways markets, extended overbought stocks (RSI > 75), stocks in confirmed downtrends, and stocks with binary events (earnings, FDA) within 7 days
- You always anchor stop-losses to a technical level (below support, below a key MA), never arbitrary round numbers

## Hard risk rules (non-negotiable — built into the system)
1. AT MOST ONE trade per run. You pick exactly one stock, or NO_TRADE.
2. The bot now scans FREQUENTLY (every couple of days), so you are NOT forced to trade. NO_TRADE is a legitimate, encouraged output when no candidate offers a genuinely good risk/reward setup — another scan comes in a couple of days. A forced mediocre trade is worse than waiting. Quality over activity.
3. That said, do not be timid: if a candidate has a clean, high-probability setup that clears the quality bar (ACCEPTABLE tier or better), take it. Reserve NO_TRADE for weeks where the best setup is genuinely weak, broken, or fighting the market regime.
4. Stop-loss is mandatory. Every trade must have a specific stop-loss price.
5. Never recommend a stock with earnings announced in the next 7 days (these are pre-filtered, but double-check your reasoning).
6. Maximum position size is 5% of capital — this is enforced downstream, not your concern here.

## Market regime (read this first)
You are given the current broad-market regime (RISK_ON / NEUTRAL / RISK_OFF) computed from SPY and QQQ:
- RISK_ON: trade your best setup normally. Long setups have the wind at their back.
- NEUTRAL: be selective. Favour STANDARD/PREMIUM setups; demand clean technicals.
- RISK_OFF: the market is falling. Long trades are swimming upstream. Only take a trade if the setup is exceptional (PREMIUM, strong stock-specific catalyst, clear support). Otherwise return NO_TRADE and cite the regime. Do NOT force a long into a down market.

## Using the data you are given
Each candidate comes with: price/trend/RSI, moving averages, ATR, MACD, Bollinger bands, support/resistance, the last 10 daily candles, news sentiment with headlines, and Wall Street analyst signals (recommendation consensus + price target).
- Lead with PRICE ACTION and TECHNICALS — the candles, trend, levels, and risk/reward define the trade. This is a technical swing, not a fundamentals bet.
- RELATIVE STRENGTH: prefer stocks outperforming SPY (positive RS). Leaders continue to lead; avoid laggards making new relative lows unless it's a clean oversold bounce with a catalyst.
- ADX (trend strength): ADX ≥ 25 = a real trend you can swing. ADX < 20 = choppy/rangebound — entries there often chop you out; demand a tighter setup or pass.
- Use NEWS as a catalyst/context check: a bullish catalyst strengthens a long; a fresh bearish headline (lawsuit, downgrade, guidance cut) is a reason to pass even on a clean chart.
- Use WALL STREET signals as confirmation only, never as a trigger. A BUY consensus with meaningful price-target upside corroborates a long; a SELL consensus or a price target BELOW current price is a yellow flag — don't fight it without a strong technical reason. Missing analyst data is fine — just lean on technicals.

## Price zone rules
Each candidate is tagged GREEN or BUFFER:
- GREEN ($10–$150): can be selected at any quality tier (PREMIUM, STANDARD, ACCEPTABLE, BELOW_BAR)
- BUFFER ($8–$10 or $150–$175): may ONLY be selected if the setup qualifies as PREMIUM (R:R >= 3.0 AND target_move_pct >= 10%). If a buffer-zone stock's best setup is not PREMIUM, skip it and pick the next best green-zone candidate instead. The system will hard-reject a buffer-zone pick that is not PREMIUM.

## Graduated target move search (apply in order every week)
The user is doing weekly swing trades (5–7 day holding period) on a small account ($250) with monthly capital injections and compounding. Each trade must deliver MEANINGFUL ABSOLUTE upside — a high R:R ratio on a tiny move is not worth a week of capital and attention.

Search for the best setup using this priority order:
1. FIRST — Look for setups with target move ≥ 10% from entry AND R:R ≥ 2.5. If found, pick the best one. This is a PREMIUM setup.
2. SECOND — If no 10%+ setup exists, look for target move ≥ 8% AND R:R ≥ 2.5. Pick the best one. This is STANDARD.
3. THIRD — If no 8%+ setup exists, look for target move ≥ 6% AND R:R ≥ 2.5. Pick the best one. This is ACCEPTABLE.
4. FLOOR — If nothing reaches 6%, return the best setup available regardless. Flag it as BELOW_BAR.

In your rationale, state which tier you landed at (e.g. "Found 10%+ target — PREMIUM setup" or "Best available was 7% target — no 10% setups this week").

## How to set entry, stop, and target
- Entry price: the ideal limit order price for Monday morning. Use the nearest support level, MA, or breakout level as your anchor. Be specific — a single price, not a range.
- Stop-loss: just below the nearest technical support or key MA. Must be below entry for a BUY. Give yourself a small buffer (0.5–1%) below the level so normal intraday noise doesn't stop you out.
- Target: the next meaningful resistance level, measured move, or Fibonacci extension. Must be above entry for a BUY.
- Recalculate R:R yourself: (target - entry) / (entry - stop). Report this number.
- Calculate target_move_pct: ((target - entry) / entry) * 100. Round to 1 decimal place.
- Assign quality_tier using this exact logic:
  - "PREMIUM"    if R:R >= 3.0 AND target_move_pct >= 10
  - "STANDARD"   if R:R >= 2.5 AND target_move_pct >= 8
  - "ACCEPTABLE" if R:R >= 2.5 AND target_move_pct >= 6
  - "BELOW_BAR"  for anything else
- Set meets_quality_bar: true if quality_tier is PREMIUM, STANDARD, or ACCEPTABLE. False if BELOW_BAR.
- Set is_premium: true only if quality_tier is PREMIUM. False otherwise.

## Output format
You must respond with ONLY a valid JSON object — no explanation, no markdown, no preamble, no text after the JSON.

For a trade recommendation:
{
  "decision": "TRADE",
  "symbol": "AAPL",
  "action": "BUY",
  "entry_price": 185.50,
  "stop_loss": 181.00,
  "target_price": 205.85,
  "risk_reward_ratio": 4.38,
  "target_move_pct": 11.0,
  "quality_tier": "PREMIUM",
  "meets_quality_bar": true,
  "is_premium": true,
  "timeframe": "5-7 days",
  "confidence": "HIGH",
  "rationale": "Two to four sentences explaining the setup. State which quality tier was reached and why.",
  "key_risks": ["Risk 1", "Risk 2"],
  "no_trade_reason": null
}

For no trade:
{
  "decision": "NO_TRADE",
  "symbol": null,
  "action": null,
  "entry_price": null,
  "stop_loss": null,
  "target_price": null,
  "risk_reward_ratio": null,
  "target_move_pct": null,
  "quality_tier": null,
  "meets_quality_bar": null,
  "is_premium": null,
  "timeframe": null,
  "confidence": null,
  "rationale": null,
  "key_risks": [],
  "no_trade_reason": "Concise explanation of why no setup qualifies this week."
}

## Confidence levels
- HIGH: clear pattern, strong catalyst, obvious technical levels, high-conviction setup
- MEDIUM: decent setup but one element is uncertain (e.g. weak catalyst, resistance nearby)
- LOW: marginal setup — consider whether BELOW_BAR is more honest

## Final instruction
Review all candidates carefully. Think through each one. Then commit to your single best pick or NO_TRADE. Be disciplined — a mediocre trade forced through is worse than sitting out a week."""


def _get_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(
            api_key=config.ANTHROPIC_API_KEY,
            timeout=config.ANALYST_TIMEOUT_SECS,
        )
    return _anthropic_client


# ── Prompt formatting ─────────────────────────────────────────────────────────

def _format_candidate(candidate: dict) -> str:
    """Format one enriched candidate as a readable text block for the prompt."""
    sym = candidate["symbol"]
    t = candidate.get("technicals", {})
    n = candidate.get("news", {})
    sig = candidate.get("analyst_signals", {}) or {}
    s = candidate  # scanner fields live at the top level

    support_str = " / ".join(f"${v}" for v in t.get("support_levels", [])) or "none detected"
    resistance_str = " / ".join(f"${v}" for v in t.get("resistance_levels", [])) or "none detected"
    headlines = n.get("top_headlines", [])
    headline_str = "\n".join(f"    - {h}" for h in headlines) if headlines else "    - No headlines found"

    # Recent daily candles (last 10) — lets Claude read the actual price action /
    # patterns rather than only summary stats.
    candles = t.get("recent_candles", [])
    if candles:
        candle_lines = "\n".join(
            f"    {c['date']}: O {c['open']} H {c['high']} L {c['low']} C {c['close']} V {c['volume']:,}"
            for c in candles
        )
    else:
        candle_lines = "    (no candle data)"

    # Wall Street analyst signals (Finnhub)
    rec = sig.get("recommendation") or {}
    pt = sig.get("price_target") or {}
    if rec:
        wall_st_str = (
            f"{rec.get('consensus', 'N/A')} consensus "
            f"({rec.get('strongBuy', 0)} strong buy / {rec.get('buy', 0)} buy / "
            f"{rec.get('hold', 0)} hold / {rec.get('sell', 0)} sell / "
            f"{rec.get('strongSell', 0)} strong sell — {rec.get('bullish_pct', 0):.0f}% bullish)"
        )
    else:
        wall_st_str = "no analyst coverage data"
    if pt and pt.get("mean"):
        upside = pt.get("upside_pct")
        upside_str = f", {upside:+.1f}% vs current" if upside is not None else ""
        price_target_str = f"mean ${pt['mean']} (range ${pt.get('low')}–${pt.get('high')}{upside_str})"
    else:
        price_target_str = "no price target data"

    price_zone = s.get("price_zone", "GREEN")
    zone_note = " ⚠️ BUFFER ZONE — only pickable if PREMIUM" if price_zone == "BUFFER" else ""

    rs = s.get("rel_strength")
    rs_str = f"{rs:+.1f}pp vs SPY (60d)" if rs is not None else "n/a"
    adx = t.get("adx")
    if adx is not None:
        if adx >= config.ADX_STRONG:
            adx_str = f"{adx} (STRONG trend)"
        elif adx < config.ADX_CHOPPY:
            adx_str = f"{adx} (CHOPPY — be wary)"
        else:
            adx_str = f"{adx} (moderate)"
    else:
        adx_str = "n/a"

    return f"""
=== {sym} ==={zone_note}
Price: ${t.get('last_close', s.get('last_close', 'N/A'))} | Zone: {price_zone} | Trend: {t.get('trend', 'N/A')} | RSI: {t.get('rsi', s.get('rsi', 'N/A'))}
Relative strength: {rs_str} | ADX: {adx_str}
MA20: ${t.get('ma20', 'N/A')} | MA50: ${t.get('ma50', 'N/A')} | MA200: ${t.get('ma200', 'N/A')}
ATR(14): ${t.get('atr', 'N/A')} ({t.get('atr_pct', 'N/A')}% of price)
MACD line: {t.get('macd_line', 'N/A')} | Histogram: {t.get('macd_histogram', 'N/A')}
Bollinger: Upper ${t.get('bb_upper', 'N/A')} / Lower ${t.get('bb_lower', 'N/A')}
Support:    {support_str}
Resistance: {resistance_str}
Volume: {t.get('last_volume', s.get('vol_20d_avg', 'N/A'))} ({t.get('vol_ratio', s.get('volume_ratio', 'N/A'))}x 20d avg)
News sentiment: {n.get('overall_sentiment', 'NEUTRAL')} ({n.get('bullish_count', 0)} bullish / {n.get('bearish_count', 0)} bearish / {n.get('neutral_count', 0)} neutral)
Wall St analysts: {wall_st_str}
Price target: {price_target_str}
Top headlines:
{headline_str}
Recent daily candles (oldest→newest):
{candle_lines}
Scanner score: {s.get('score', 'N/A')}""".strip()


def build_prompt(candidates: list[dict], regime: Optional[dict] = None,
                 track_record: str = "") -> str:
    """Build the user-turn message containing all candidate data."""
    blocks = [_format_candidate(c) for c in candidates]
    candidates_text = "\n\n".join(blocks)

    regime_block = ""
    if regime:
        regime_block = (
            f"## CURRENT MARKET REGIME: {regime.get('regime', 'NEUTRAL')}\n"
            f"{regime.get('summary', '')}\n"
            f"Factor this into your decision per the regime rules above.\n\n"
        )

    record_block = f"{track_record}\n" if track_record else ""

    return (
        f"{regime_block}"
        f"{record_block}"
        f"Review these {len(candidates)} swing trade candidates for the next few days. "
        f"Take your time and be thorough — work through each candidate methodically "
        f"before committing. There is no rush; the goal is the single best risk-adjusted "
        f"trade, or NO_TRADE if nothing is genuinely good.\n\n"
        f"{candidates_text}\n\n"
        f"Now output your decision as a single valid JSON object."
    )


# ── Claude API call ───────────────────────────────────────────────────────────

def _call_sonnet(user_prompt: str) -> str:
    """
    Send the prompt to the analyst model (Opus 4.8) with ADAPTIVE thinking and
    return the raw text response. Adaptive thinking lets the model reason through
    each candidate privately before committing to its JSON answer; the `effort`
    setting controls how deeply it reasons. The call streams so a long
    deep-thinking request never hits a timeout.
    """
    client = _get_client()
    response = None
    with client.messages.stream(
        model=config.ANALYST_MODEL,
        max_tokens=config.ANALYST_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": config.ANALYST_EFFORT},
        system=[
            {
                "type": "text",
                "text": _ANALYST_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        response = stream.get_final_message()

    logger.info(
        "Analyst usage — model: %s, effort: %s, input: %d, output: %d, cache_read: %s, cache_create: %s",
        config.ANALYST_MODEL,
        config.ANALYST_EFFORT,
        response.usage.input_tokens,
        response.usage.output_tokens,
        getattr(response.usage, "cache_read_input_tokens", "n/a"),
        getattr(response.usage, "cache_creation_input_tokens", "n/a"),
    )
    # With adaptive thinking the response contains thinking block(s) first, then
    # the text block. Grab the text block specifically rather than content[0].
    text_block = next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)
    if text_block is None:
        raise ValueError("No text block in analyst response")
    return text_block.strip()


# ── JSON parsing ──────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict:
    """
    Parse JSON from Claude's response.
    Handles markdown code fences and stray text before/after the JSON object.
    """
    # Strip ```json ... ``` fences
    if "```" in raw:
        raw = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Find the outermost {...} block
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start: end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract valid JSON from response: {raw[:200]!r}")


# ── Validation ────────────────────────────────────────────────────────────────

def _validate(result: dict) -> tuple[bool, str]:
    """
    Validate a TRADE response. Recalculates R:R, target_move_pct, quality_tier,
    is_premium, and meets_quality_bar from raw prices — never trusts Claude's values.
    Structurally broken trades hard-reject; quality issues pass through with flags.
    """
    if result.get("decision") == "NO_TRADE":
        return True, ""

    required = ["symbol", "action", "entry_price", "stop_loss", "target_price"]
    for field in required:
        if result.get(field) is None:
            return False, f"Missing required field: {field}"

    entry = result.get("entry_price")
    stop = result.get("stop_loss")
    target = result.get("target_price")
    action = result.get("action", "BUY").upper()

    try:
        entry, stop, target = float(entry), float(stop), float(target)
    except (TypeError, ValueError):
        return False, "entry_price / stop_loss / target_price must be numeric"

    if action == "BUY":
        if stop >= entry:
            return False, f"BUY stop_loss ({stop}) must be below entry ({entry})"
        if target <= entry:
            return False, f"BUY target ({target}) must be above entry ({entry})"
    elif action == "SELL_SHORT":
        if stop <= entry:
            return False, f"SHORT stop_loss ({stop}) must be above entry ({entry})"
        if target >= entry:
            return False, f"SHORT target ({target}) must be below entry ({entry})"

    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk == 0:
        return False, "Risk is zero (entry == stop)"

    actual_rr = round(reward / risk, 4)
    target_move_pct = round((reward / entry) * 100, 1)

    # Determine quality tier from recalculated numbers
    if actual_rr >= 3.0 and target_move_pct >= 10:
        quality_tier = "PREMIUM"
    elif actual_rr >= config.MIN_RISK_REWARD and target_move_pct >= 8:
        quality_tier = "STANDARD"
    elif actual_rr >= config.MIN_RISK_REWARD and target_move_pct >= 6:
        quality_tier = "ACCEPTABLE"
    else:
        quality_tier = "BELOW_BAR"

    result["risk_reward_ratio"] = round(actual_rr, 2)
    result["target_move_pct"] = target_move_pct
    result["quality_tier"] = quality_tier
    result["is_premium"] = quality_tier == "PREMIUM"
    result["meets_quality_bar"] = quality_tier != "BELOW_BAR"

    if quality_tier == "BELOW_BAR":
        logger.warning(
            "Quality BELOW_BAR: R:R=%.4f target_move=%.1f%% — flagging, not rejecting",
            actual_rr, target_move_pct,
        )
    else:
        logger.info("Quality tier: %s | R:R=%.2f | target_move=%.1f%%",
                    quality_tier, actual_rr, target_move_pct)

    return True, ""


def _no_trade(reason: str) -> dict:
    return {
        "decision": "NO_TRADE",
        "symbol": None,
        "action": None,
        "entry_price": None,
        "stop_loss": None,
        "target_price": None,
        "risk_reward_ratio": None,
        "target_move_pct": None,
        "quality_tier": None,
        "meets_quality_bar": None,
        "is_premium": None,
        "timeframe": None,
        "confidence": None,
        "rationale": None,
        "key_risks": [],
        "no_trade_reason": reason,
    }


# ── Master function ───────────────────────────────────────────────────────────

def _price_zone_of(symbol: str, candidates: list[dict]) -> str:
    """Look up the price_zone tag for a symbol from the candidates list."""
    for c in candidates:
        if c.get("symbol") == symbol:
            return c.get("price_zone", "GREEN")
    return "GREEN"


def analyze(candidates: list[dict], regime: Optional[dict] = None,
            track_record: str = "") -> dict:
    """
    Run the full analyst pipeline:
      1. Build prompt from enriched candidates (+ market regime context)
      2. Call the analyst model (Opus 4.8, extended thinking)
      3. Parse and validate the JSON response
      4. Apply strict-quality discipline (BELOW_BAR → NO_TRADE)
      5. Return a clean decision dict (TRADE or NO_TRADE)

    Never raises — any failure returns NO_TRADE with an explanatory reason.
    """
    if not candidates:
        logger.warning("No candidates passed to analyst")
        return _no_trade("No candidates survived earnings and scanner filters.")

    if not config.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set")
        return _no_trade("Anthropic API key not configured.")

    user_prompt = build_prompt(candidates, regime, track_record)

    # ── Call Sonnet ───────────────────────────────────────────────────────────
    try:
        raw = _call_sonnet(user_prompt)
    except Exception as e:
        logger.error("Sonnet API call failed: %s", e)
        return _no_trade(f"Claude API error: {e}")

    # ── Parse JSON ────────────────────────────────────────────────────────────
    try:
        result = _extract_json(raw)
    except ValueError as e:
        logger.error("JSON parse failed: %s | raw: %.300s", e, raw)
        return _no_trade(f"Could not parse Claude response as JSON.")

    # ── Validate ──────────────────────────────────────────────────────────────
    valid, reason = _validate(result)
    if not valid:
        logger.warning("Validation failed — forcing NO_TRADE. Reason: %s", reason)
        return _no_trade(f"Trade rejected by risk validation: {reason}")

    # ── Strict quality discipline ─────────────────────────────────────────────
    # Frequency up, quality up: because the bot scans every couple of days, we
    # are not forced to send a weak pick. A BELOW_BAR setup becomes NO_TRADE.
    if (
        config.STRICT_QUALITY
        and result.get("decision") == "TRADE"
        and result.get("quality_tier") == "BELOW_BAR"
    ):
        logger.info(
            "STRICT_QUALITY: %s pick is BELOW_BAR (R:R=%s, move=%s%%) — converting to NO_TRADE",
            result.get("symbol"), result.get("risk_reward_ratio"), result.get("target_move_pct"),
        )
        return _no_trade(
            f"Best available setup ({result.get('symbol')}) was below the quality bar "
            f"(R:R 1:{result.get('risk_reward_ratio')}, target move {result.get('target_move_pct')}%). "
            f"Holding out for a better setup — next scan in {config.CADENCE_LABEL}."
        )

    # ── Buffer zone enforcement ───────────────────────────────────────────────
    if result.get("decision") == "TRADE":
        picked_symbol = result.get("symbol")
        zone = _price_zone_of(picked_symbol, candidates)
        if zone == "BUFFER" and result.get("quality_tier") != "PREMIUM":
            logger.warning(
                "Buffer zone rejection: %s picked but quality_tier=%s (need PREMIUM)",
                picked_symbol, result.get("quality_tier"),
            )
            return _no_trade(
                f"{picked_symbol} is in the buffer price zone (${result.get('entry_price')}) "
                f"and requires a PREMIUM setup (R:R >= 3.0, target >= 10%%). "
                f"Best setup was {result.get('quality_tier')} — no green-zone alternative available."
            )

    decision = result.get("decision", "NO_TRADE")
    logger.info(
        "Analyst decision: %s | symbol=%s | R:R=%s | tier=%s | move=%s%% | confidence=%s",
        decision,
        result.get("symbol"),
        result.get("risk_reward_ratio"),
        result.get("quality_tier"),
        result.get("target_move_pct"),
        result.get("confidence"),
    )
    return result
