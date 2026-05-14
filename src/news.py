import json
import logging
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Optional

import requests
import anthropic

import config

logger = logging.getLogger(__name__)

# Cached Anthropic client — reused across calls within a run
_anthropic_client: Optional[anthropic.Anthropic] = None

# System prompt for Haiku sentiment tagging — static so it qualifies for prompt caching
_HAIKU_SYSTEM_PROMPT = """You are a financial news sentiment analyst. Your job is to tag each headline for a specific stock with its market sentiment.

For each headline provided, output a JSON object with:
- "headline": the original headline text (string)
- "sentiment": one of "BULLISH", "BEARISH", or "NEUTRAL" (string)
- "confidence": a float between 0.0 and 1.0 indicating how clear the sentiment is
- "reason": one short phrase explaining your call — NO quotes, NO commas inside the reason (string)

Rules:
- BULLISH: news that could drive the stock price up (earnings beat, new product, partnership, buyback, upgrade, strong guidance, macro tailwind)
- BEARISH: news that could drive the stock price down (earnings miss, lawsuit, regulatory action, CEO departure, downgrade, macro headwind, competition)
- NEUTRAL: news with no clear price direction (routine filing, index rebalancing, minor operational update)
- Focus only on impact to THIS specific stock, not the broader market
- When in doubt, lean NEUTRAL rather than forcing a direction

CRITICAL OUTPUT RULES:
- Return ONLY a raw JSON array. No markdown, no code fences, no preamble, no explanation after.
- Every string value must be on a single line — no newlines inside strings.
- Keep "reason" under 10 words. Never use double-quotes inside a reason string.
- The array must be valid JSON that json.loads() can parse directly.

Example of correct output (copy this exact format):
[{"headline":"Apple reports record sales","sentiment":"BULLISH","confidence":0.85,"reason":"Strong revenue beat"},{"headline":"CEO steps down","sentiment":"BEARISH","confidence":0.9,"reason":"Leadership uncertainty"}]"""


def _get_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _anthropic_client


def _date_from(days: int) -> str:
    return (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")


# ── Fetchers ──────────────────────────────────────────────────────────────────

def fetch_newsapi(symbol: str, company_name: str, days: int = 7) -> list[dict]:
    """
    Fetch recent articles from NewsAPI using the company name as keyword.
    Returns a list of article dicts with: title, source, published_at, url.
    """
    if not config.NEWSAPI_KEY:
        logger.debug("NEWSAPI_KEY not set — skipping NewsAPI for %s", symbol)
        return []

    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": company_name,
                "from": _date_from(days),
                "sortBy": "relevancy",
                "language": "en",
                "pageSize": 10,
                "apiKey": config.NEWSAPI_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        result = [
            {
                "title": a.get("title", "").strip(),
                "source": a.get("source", {}).get("name", ""),
                "published_at": a.get("publishedAt", ""),
                "url": a.get("url", ""),
                "origin": "newsapi",
            }
            for a in articles
            if a.get("title") and a.get("title") != "[Removed]"
        ]
        logger.debug("NewsAPI returned %d articles for %s", len(result), symbol)
        return result

    except Exception as e:
        logger.warning("NewsAPI failed for %s: %s", symbol, e)
        return []


def fetch_marketaux(symbol: str, days: int = 7) -> list[dict]:
    """
    Fetch recent articles from Marketaux using the ticker symbol directly.
    Marketaux is ticker-aware so results are more precise than keyword search.
    """
    if not config.MARKETAUX_API_KEY:
        logger.debug("MARKETAUX_API_KEY not set — skipping Marketaux for %s", symbol)
        return []

    try:
        resp = requests.get(
            "https://api.marketaux.com/v1/news/all",
            params={
                "symbols": symbol,
                "filter_entities": "true",
                "language": "en",
                "published_after": _date_from(days),
                "api_token": config.MARKETAUX_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        articles = resp.json().get("data", [])
        result = [
            {
                "title": a.get("title", "").strip(),
                "source": a.get("source", ""),
                "published_at": a.get("published_at", ""),
                "url": a.get("url", ""),
                "origin": "marketaux",
            }
            for a in articles
            if a.get("title")
        ]
        logger.debug("Marketaux returned %d articles for %s", len(result), symbol)
        return result

    except Exception as e:
        logger.warning("Marketaux failed for %s: %s", symbol, e)
        return []


# ── Deduplication ─────────────────────────────────────────────────────────────

def _deduplicate(articles: list[dict], threshold: float = 0.85) -> list[dict]:
    """
    Remove near-duplicate articles using title similarity.
    When two titles have SequenceMatcher ratio >= threshold, keep the first seen.
    """
    unique = []
    for article in articles:
        title = article.get("title", "")
        is_dupe = any(
            SequenceMatcher(None, title.lower(), seen.get("title", "").lower()).ratio() >= threshold
            for seen in unique
        )
        if not is_dupe:
            unique.append(article)
    return unique


# ── Haiku sentiment tagging ───────────────────────────────────────────────────

_MAX_HEADLINES_FOR_HAIKU = 8


def _haiku_call(titles: list[str], symbol: str) -> list[dict]:
    """Make one Haiku API call and return the parsed JSON list. Raises on failure."""
    user_content = (
        f"Tag sentiment for stock {symbol}. Return ONLY a JSON array, nothing else.\n\n"
        + json.dumps(titles)   # compact, no indent — reduces token count and parse risk
    )
    client = _get_client()
    response = client.messages.create(
        model=config.FILTER_MODEL,
        max_tokens=800,
        system=[
            {
                "type": "text",
                "text": _HAIKU_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
    )
    raw = response.content[0].text.strip()

    # Strip markdown fences if Haiku adds them despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    result = json.loads(raw)   # raises JSONDecodeError on bad output
    logger.debug(
        "Haiku tagged %d headlines for %s (cache_read=%s)",
        len(titles), symbol,
        getattr(response.usage, "cache_read_input_tokens", "n/a"),
    )
    return result


def _apply_tags(articles: list[dict], tagged: list[dict]) -> None:
    """Merge Haiku tags back onto article dicts in-place by position."""
    for i, article in enumerate(articles):
        if i < len(tagged):
            article["sentiment"] = tagged[i].get("sentiment", "NEUTRAL")
            article["confidence"] = tagged[i].get("confidence", 0.5)
            article["reason"] = tagged[i].get("reason", "")
        else:
            article.update({"sentiment": "NEUTRAL", "confidence": 0.5, "reason": ""})


def _default_neutral(articles: list[dict]) -> None:
    for a in articles:
        a.setdefault("sentiment", "NEUTRAL")
        a.setdefault("confidence", 0.5)
        a.setdefault("reason", "")


def tag_sentiment_haiku(articles: list[dict], symbol: str) -> list[dict]:
    """
    Send article titles to Claude Haiku for sentiment tagging.
    - Caps input at 8 headlines to reduce token count and parse risk.
    - Retries once on JSON parse failure before falling back to NEUTRAL.
    - System prompt is prompt-cached (static across all calls in a session).
    """
    if not articles:
        return []

    if not config.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — skipping Haiku sentiment for %s", symbol)
        _default_neutral(articles)
        return articles

    # Cap headlines sent to Haiku
    articles_to_tag = articles[:_MAX_HEADLINES_FOR_HAIKU]
    titles = [a.get("title", "") for a in articles_to_tag]

    # Try once, retry once on JSON parse failure, then fall back
    for attempt in range(2):
        try:
            tagged = _haiku_call(titles, symbol)
            _apply_tags(articles_to_tag, tagged)
            # Any articles beyond the cap default to NEUTRAL
            for a in articles[_MAX_HEADLINES_FOR_HAIKU:]:
                _default_neutral([a])
            return articles
        except json.JSONDecodeError as e:
            if attempt == 0:
                logger.warning(
                    "Haiku JSON parse failed for %s (attempt 1): %s — retrying", symbol, e
                )
            else:
                logger.warning(
                    "Haiku JSON parse failed for %s (attempt 2): %s — defaulting to NEUTRAL",
                    symbol, e,
                )
        except Exception as e:
            logger.warning("Haiku call failed for %s: %s — defaulting to NEUTRAL", symbol, e)
            break

    _default_neutral(articles)
    return articles


# ── Master function ───────────────────────────────────────────────────────────

def get_news_summary(symbol: str, company_name: Optional[str] = None) -> dict:
    """
    Fetch, deduplicate, and sentiment-tag news for one stock.
    Returns a structured summary dict consumed by analyst.py.
    """
    if company_name is None:
        company_name = config.SYMBOL_TO_COMPANY.get(symbol, symbol)

    # Fetch from both sources, deduplicate
    newsapi_articles = fetch_newsapi(symbol, company_name)
    marketaux_articles = fetch_marketaux(symbol)
    combined = _deduplicate(newsapi_articles + marketaux_articles)

    if not combined:
        logger.info("No news found for %s", symbol)
        return _empty_summary(symbol)

    # Tag sentiment via Haiku
    tagged = tag_sentiment_haiku(combined, symbol)

    # Tally
    counts = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
    for a in tagged:
        counts[a.get("sentiment", "NEUTRAL")] += 1

    overall = max(counts, key=counts.get)

    # Top 3 headlines: highest-confidence non-neutral first, then by confidence
    sorted_articles = sorted(
        tagged,
        key=lambda a: (a.get("sentiment") != "NEUTRAL", a.get("confidence", 0)),
        reverse=True,
    )
    top_headlines = [a["title"] for a in sorted_articles[:3]]

    return {
        "symbol": symbol,
        "articles": tagged,
        "article_count": len(tagged),
        "bullish_count": counts["BULLISH"],
        "bearish_count": counts["BEARISH"],
        "neutral_count": counts["NEUTRAL"],
        "overall_sentiment": overall,
        "top_headlines": top_headlines,
    }


def _empty_summary(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "articles": [],
        "article_count": 0,
        "bullish_count": 0,
        "bearish_count": 0,
        "neutral_count": 0,
        "overall_sentiment": "NEUTRAL",
        "top_headlines": [],
    }
