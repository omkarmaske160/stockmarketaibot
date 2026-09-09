"""
Optional extra features shared by the dashboard and the hourly checker:
- Live news headlines via Google News RSS (free, no API key needed)
- Sector/industry lookup via yfinance
- Telegram alert sending (in addition to email)
"""

import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests
import yfinance as yf


def get_news_headlines(query, max_items=4):
    """
    Fetches recent headlines for a search query using Google News' public
    RSS feed - no API key or signup needed. Returns a list of
    {"title": ..., "link": ...} dicts, or an empty list on any failure.
    """
    try:
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
        resp = requests.get(url, timeout=10)
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")[:max_items]
        headlines = []
        for item in items:
            title_el = item.find("title")
            link_el = item.find("link")
            if title_el is not None and title_el.text:
                headlines.append({
                    "title": title_el.text,
                    "link": link_el.text if link_el is not None else None,
                })
        return headlines
    except Exception:
        return []


def get_sector_industry_info(symbol):
    """Returns (sector, industry) strings for an NSE symbol, or ('Unknown','Unknown')."""
    try:
        info = yf.Ticker(symbol + ".NS").info
        return info.get("sector", "Unknown"), info.get("industry", "Unknown")
    except Exception:
        return "Unknown", "Unknown"


def send_telegram_message(bot_token, chat_id, message):
    """Sends a message via a Telegram bot. Returns True on success."""
    if not bot_token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(
            url, json={"chat_id": chat_id, "text": message}, timeout=10
        )
        return resp.status_code == 200
    except Exception:
        return False
