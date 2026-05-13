import logging

import requests

import config

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.telegram.org/bot{token}/{method}"


def send_message(text: str, parse_mode: str = "MarkdownV2") -> bool:
    """
    Send a message to the configured Telegram chat.
    Returns True on success, False on any failure — never raises.
    Uses the Telegram Bot HTTP API directly via requests.
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — cannot send message")
        return False

    url = _BASE_URL.format(token=config.TELEGRAM_BOT_TOKEN, method="sendMessage")

    try:
        resp = requests.post(
            url,
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": parse_mode,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            logger.error("Telegram API returned ok=false: %s", data)
            return False

        logger.info("Telegram message sent (message_id=%s)", data.get("result", {}).get("message_id"))
        return True

    except requests.exceptions.Timeout:
        logger.error("Telegram send timed out after 15s")
        return False
    except requests.exceptions.HTTPError as e:
        # Log the full Telegram error description for easier debugging
        try:
            detail = e.response.json().get("description", str(e))
        except Exception:
            detail = str(e)
        logger.error("Telegram HTTP error: %s", detail)
        return False
    except Exception as e:
        logger.error("Telegram send failed: %s", e)
        return False


def test_telegram() -> bool:
    """Send a test ping to confirm the bot token and chat ID are working."""
    logger.info("Sending Telegram test message...")
    return send_message(
        "🤖 SwingBot online\\. Test message — if you see this, Telegram is configured correctly\\.",
        parse_mode="MarkdownV2",
    )
