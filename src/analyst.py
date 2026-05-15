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
1. ONE trade per week maximum. You must pick exactly one stock. Only use NO_TRADE if every single candidate has a structurally broken setup (e.g. stop above entry, non-numeric prices, missing critical data).
2. Always pick your BEST candidate. Only use NO_TRADE as a last resort — not a quality filter.
3. Stop-loss is mandatory. Every trade must have a specific stop-loss price.
4. Never recommend a stock with earnings announced in the next 7 days (these are pre-filtered, but double-check your reasoning).
5. Maximum position size is 5% of capital — this is enforced downstream, not your concern here.

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
        _anthropic_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _anthropic_client


# ── Prompt formatting ─────────────────────────────────────────────────────────

def _format_candidate(candidate: dict) -> str:
    """Format one enriched candidate as a readable text block for the prompt."""
    sym = candidate["symbol"]
    t = candidate.get("technicals", {})
    n = candidate.get("news", {})
    s = candidate  # scanner fields live at the top level

    support_str = " / ".join(f"${v}" for v in t.get("support_levels", [])) or "none detected"
    resistance_str = " / ".join(f"${v}" for v in t.get("resistance_levels", [])) or "none detected"
    headlines = n.get("top_headlines", [])
    headline_str = "\n".join(f"    - {h}" for h in headlines) if headlines else "    - No headlines found"

    return f"""
=== {sym} ===
Price: ${t.get('last_close', s.get('last_close', 'N/A'))} | Trend: {t.get('trend', 'N/A')} | RSI: {t.get('rsi', s.get('rsi', 'N/A'))}
MA20: ${t.get('ma20', 'N/A')} | MA50: ${t.get('ma50', 'N/A')} | MA200: ${t.get('ma200', 'N/A')}
ATR(14): ${t.get('atr', 'N/A')} ({t.get('atr_pct', 'N/A')}% of price)
MACD line: {t.get('macd_line', 'N/A')} | Histogram: {t.get('macd_histogram', 'N/A')}
Bollinger: Upper ${t.get('bb_upper', 'N/A')} / Lower ${t.get('bb_lower', 'N/A')}
Support:    {support_str}
Resistance: {resistance_str}
Volume: {t.get('last_volume', s.get('vol_20d_avg', 'N/A'))} ({t.get('vol_ratio', s.get('volume_ratio', 'N/A'))}x 20d avg)
News sentiment: {n.get('overall_sentiment', 'NEUTRAL')} ({n.get('bullish_count', 0)} bullish / {n.get('bearish_count', 0)} bearish / {n.get('neutral_count', 0)} neutral)
Top headlines:
{headline_str}
Scanner score: {s.get('score', 'N/A')}""".strip()


def build_prompt(candidates: list[dict]) -> str:
    """Build the user-turn message containing all candidate data."""
    blocks = [_format_candidate(c) for c in candidates]
    candidates_text = "\n\n".join(blocks)

    return (
        f"Review these {len(candidates)} swing trade candidates for the upcoming week. "
        f"Pick exactly one trade or output NO_TRADE.\n\n"
        f"{candidates_text}\n\n"
        f"Now output your decision as a single valid JSON object."
    )


# ── Claude API call ───────────────────────────────────────────────────────────

def _call_sonnet(user_prompt: str) -> str:
    """Send the prompt to Claude Sonnet and return the raw text response."""
    client = _get_client()
    response = client.messages.create(
        model=config.ANALYST_MODEL,
        max_tokens=1500,
        system=[
            {
                "type": "text",
                "text": _ANALYST_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )
    logger.info(
        "Sonnet usage — input: %d, output: %d, cache_read: %s, cache_create: %s",
        response.usage.input_tokens,
        response.usage.output_tokens,
        getattr(response.usage, "cache_read_input_tokens", "n/a"),
        getattr(response.usage, "cache_creation_input_tokens", "n/a"),
    )
    return response.content[0].text.strip()


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

def analyze(candidates: list[dict]) -> dict:
    """
    Run the full analyst pipeline:
      1. Build prompt from enriched candidates
      2. Call Claude Sonnet
      3. Parse and validate the JSON response
      4. Return a clean decision dict (TRADE or NO_TRADE)

    Never raises — any failure returns NO_TRADE with an explanatory reason.
    """
    if not candidates:
        logger.warning("No candidates passed to analyst")
        return _no_trade("No candidates survived earnings and scanner filters.")

    if not config.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set")
        return _no_trade("Anthropic API key not configured.")

    user_prompt = build_prompt(candidates)

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
