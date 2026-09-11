"""
Runs independently of the dashboard (triggered hourly by GitHub Actions).
Reads watchlist.txt and price_targets.json (both may have been updated by
the dashboard via GitHub sync), checks each stock's AI signal, last-hour
price move, and any price-target alerts, then emails (and optionally
Telegrams) a report.
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
import pandas as pd
import yfinance as yf

from signal_utils import compute_features, train_and_predict, explain_signal
from extras import send_telegram_message

WATCHLIST_FILE = "watchlist.txt"
TARGETS_FILE = "price_targets.json"
BIG_MOVE_THRESHOLD = 2.0  # percent move in the last hour to flag as notable


def load_watchlist():
    if not os.path.exists(WATCHLIST_FILE):
        return []
    with open(WATCHLIST_FILE) as f:
        return [line.strip().upper() for line in f if line.strip()]


def load_price_targets():
    if not os.path.exists(TARGETS_FILE):
        return {}
    try:
        with open(TARGETS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def get_daily_data(symbol):
    df = yf.download(symbol + ".NS", period="5y", interval="1d", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def get_recent_intraday(symbol):
    try:
        df = yf.download(symbol + ".NS", period="1d", interval="5m", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return pd.DataFrame()


def hourly_change_pct(intraday_df):
    if intraday_df.empty or len(intraday_df) < 2:
        return None
    now_price = float(intraday_df["Close"].iloc[-1])
    hour_ago_idx = max(0, len(intraday_df) - 13)  # ~12 candles of 5 min = 1 hour
    past_price = float(intraday_df["Close"].iloc[hour_ago_idx])
    return (now_price - past_price) / past_price * 100


def check_price_target(symbol, current_price, targets):
    target_info = targets.get(symbol)
    if not target_info:
        return None
    target_price = target_info.get("target")
    direction = target_info.get("direction", "above")
    if target_price is None:
        return None
    if direction == "above" and current_price >= target_price:
        return f"[TARGET HIT] {symbol} is now Rs.{current_price:.2f}, at/above your target of Rs.{target_price:.2f}"
    if direction == "below" and current_price <= target_price:
        return f"[TARGET HIT] {symbol} is now Rs.{current_price:.2f}, at/below your target of Rs.{target_price:.2f}"
    return None


def build_report():
    lines = []
    movers = []
    target_hits = []
    targets = load_price_targets()

    for symbol in load_watchlist():
        daily = get_daily_data(symbol)
        if daily.empty:
            continue

        close = pd.to_numeric(daily["Close"], errors="coerce").dropna()
        if close.empty:
            continue
        ath = float(close.max())
        atl = float(close.min())
        current_price = float(close.iloc[-1])

        feat_df = compute_features(daily)
        pred, prob, latest_row = train_and_predict(feat_df)

        signal = "Not enough data"
        reason_str = ""
        if pred is not None:
            direction = "UP" if pred == 1 else "DOWN"
            signal = f"{direction} ({prob*100:.1f}% confidence)"
            reasons = explain_signal(latest_row)
            reason_str = " | Why: " + "; ".join(reasons[:2])

        intraday = get_recent_intraday(symbol)
        change_pct = hourly_change_pct(intraday)
        change_str = f"{change_pct:+.2f}% in last hour" if change_pct is not None else "n/a"

        lines.append(
            f"{symbol}: Signal={signal} | Last-hour change={change_str} "
            f"| ATH=Rs.{ath:.2f} | ATL=Rs.{atl:.2f}{reason_str}"
        )

        if change_pct is not None and abs(change_pct) >= BIG_MOVE_THRESHOLD:
            movers.append(f"[ALERT] {symbol} moved {change_pct:+.2f}% in the last hour!")

        hit = check_price_target(symbol, current_price, targets)
        if hit:
            target_hits.append(hit)

    return lines, movers, target_hits


def send_email(subject, body):
    gmail_address = os.environ["GMAIL_ADDRESS"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]
    receiver_email = os.environ["RECEIVER_EMAIL"]

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = receiver_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, gmail_app_password)
        server.sendmail(gmail_address, receiver_email, msg.as_string())


def main():
    lines, movers, target_hits = build_report()
    if not lines:
        print("No data to report, skipping.")
        return

    parts = []
    if target_hits:
        parts.append("PRICE TARGETS HIT:\n" + "\n".join(target_hits))
    if movers:
        parts.append("BIG MOVERS THIS HOUR:\n" + "\n".join(movers))
    parts.append("FULL WATCHLIST REPORT:\n" + "\n".join(lines))
    body = "\n\n".join(parts)

    send_email("Hourly Stock Watchlist Report", body)
    print("Email sent.")

    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if telegram_token and telegram_chat_id:
        if send_telegram_message(telegram_token, telegram_chat_id, "📊 Hourly Stock Report\n\n" + body):
            print("Telegram message sent.")
        else:
            print("Telegram send failed.")


if __name__ == "__main__":
    main()
