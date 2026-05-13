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
- "reason": one sentence explaining your sentiment call (string)

Rules:
- BULLISH: news that could drive the stock price up (earnings beat, new product, partnership, buyback, upgrade, strong guidance, macro tailwind)
- BEARISH: news that could drive the stock price down (earnings miss, lawsuit, regulatory action, CEO departure, downgrade, macro headwind, competition)
- NEUTRAL: news with no clear price direction (routine filing, index rebalancing, minor operational update)
- Focus only on impact to THIS specific stock, not the broader market
- When in doubt, lean NEUTRAL rather than forcing a direction

Respond with ONLY a valid JSON array — no explanation, no markdown, no preamble. Example:
[
  {"headline": "...", "sentiment": "BULLISH", "confidence": 0.85, "reason": "..."},
  {"headline": "...", "sentiment": "NEUTRAL", "confidence": 0.60, "reason": "..."}
]"""


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

def tag_sentiment_haiku(articles: list[dict], symbol: str) -> list[dict]:
    """
    Send all article titles to Claude Haiku in a single batched call.
    The system prompt is marked for prompt caching (static across all calls).
    Returns the same article list with 'sentiment', 'confidence', 'reason' added.
    """
    if not articles:
        return []

    if not config.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — returning articles without sentiment")
        for a in articles:
            a.update({"sentiment": "NEUTRAL", "confidence": 0.5, "reason": "No API key"})
        return articles

    titles = [a.get("title", "") for a in articles]
    user_content = (
        f"Tag the sentiment of each headline for stock: {symbol}\n\n"
        + json.dumps(titles, indent=2)
    )

    try:
        client = _get_client()
        response = client.messages.create(
            model=config.FILTER_MODEL,
            max_tokens=1024,
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

        # Strip markdown code fences if Haiku wraps output in them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        tagged = json.loads(raw)

        # Merge sentiment back onto original article dicts by position
        for i, article in enumerate(articles):
            if i < len(tagged):
                article["sentiment"] = tagged[i].get("sentiment", "NEUTRAL")
                article["confidence"] = tagged[i].get("confidence", 0.5)
                article["reason"] = tagged[i].get("reason", "")
            else:
                article.update({"sentiment": "NEUTRAL", "confidence": 0.5, "reason": ""})

        logger.debug(
            "Haiku tagged %d articles for %s (cache: %s)",
            len(articles), symbol,
            getattr(response.usage, "cache_read_input_tokens", "n/a"),
        )
        return articles

    except (json.JSONDecodeError, IndexError) as e:
        logger.warning("Haiku response parse failed for %s: %s — defaulting to NEUTRAL", symbol, e)
        for a in articles:
            a.setdefault("sentiment", "NEUTRAL")
            a.setdefault("confidence", 0.5)
            a.setdefault("reason", "")
        return articles

    except Exception as e:
        logger.warning("Haiku tagging failed for %s: %s — defaulting to NEUTRAL", symbol, e)
        for a in articles:
            a.setdefault("sentiment", "NEUTRAL")
            a.setdefault("confidence", 0.5)
            a.setdefault("reason", "")
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
