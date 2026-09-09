import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import json
from io import StringIO
import google.generativeai as genai
import streamlit.components.v1 as components

from signal_utils import (
    compute_features,
    train_and_predict,
    explain_signal,
    confidence_label_and_color,
    backtest_accuracy,
)
from extras import get_news_headlines, get_sector_industry_info
import github_sync

st.set_page_config(
    page_title="Stock AI",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------
# Secrets / optional integrations
# ----------------------------------------------------------------------
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", None)
GITHUB_REPO = st.secrets.get("GITHUB_REPO", None)
SYNC_ENABLED = bool(GITHUB_TOKEN and GITHUB_REPO)

WATCHLIST_PATH = "watchlist.txt"
TARGETS_PATH = "price_targets.json"


def load_synced_watchlist():
    if not SYNC_ENABLED:
        return []
    content, _ = github_sync.get_file(GITHUB_TOKEN, GITHUB_REPO, WATCHLIST_PATH)
    if not content:
        return []
    return [line.strip().upper() for line in content.splitlines() if line.strip()]


def save_synced_watchlist(symbols):
    if not SYNC_ENABLED:
        return False
    content = "\n".join(symbols) + "\n"
    return github_sync.update_file(
        GITHUB_TOKEN, GITHUB_REPO, WATCHLIST_PATH, content,
        "Update watchlist from dashboard"
    )


def load_price_targets():
    if not SYNC_ENABLED:
        return {}
    content, _ = github_sync.get_file(GITHUB_TOKEN, GITHUB_REPO, TARGETS_PATH)
    if not content:
        return {}
    try:
        return json.loads(content)
    except Exception:
        return {}


def save_price_targets(targets_dict):
    if not SYNC_ENABLED:
        return False
    content = json.dumps(targets_dict, indent=2)
    return github_sync.update_file(
        GITHUB_TOKEN, GITHUB_REPO, TARGETS_PATH, content,
        "Update price targets from dashboard"
    )


# ----------------------------------------------------------------------
# Load the full list of NSE-listed stocks (for search/select box)
# ----------------------------------------------------------------------
@st.cache_data(ttl=86400)
def load_nse_stock_list():
    url = "https://archives.nseindia.com/content/equity/EQUITY_L.csv"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        df = pd.read_csv(StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]
        df = df[["SYMBOL", "NAME OF COMPANY"]].dropna()
        return df
    except Exception:
        fallback = {
            "SYMBOL": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
                       "SBIN", "ITC", "LT", "HINDUNILVR", "BHARTIARTL"],
            "NAME OF COMPANY": ["Reliance Industries", "Tata Consultancy Services",
                                 "Infosys", "HDFC Bank", "ICICI Bank",
                                 "State Bank of India", "ITC Ltd",
                                 "Larsen & Toubro", "Hindustan Unilever",
                                 "Bharti Airtel"]
        }
        return pd.DataFrame(fallback)


stock_list = load_nse_stock_list()
stock_list["label"] = stock_list["SYMBOL"] + " - " + stock_list["NAME OF COMPANY"]
symbol_to_name = dict(zip(stock_list["SYMBOL"], stock_list["NAME OF COMPANY"]))

st.title("📈 Indian Stock Market AI Dashboard")
st.caption(
    "Search NSE stocks, watch multiple at once, compare them, get AI signals "
    "with explanations and accuracy history, set price alerts, and ask the bot."
)

if not SYNC_ENABLED:
    st.warning(
        "GitHub sync isn't set up, so 'Save Watchlist' and price alerts won't "
        "persist. Add GITHUB_TOKEN and GITHUB_REPO to your secrets to enable this."
    )

# ----------------------------------------------------------------------
# Search + multi-select watchlist (pre-filled from synced watchlist)
# ----------------------------------------------------------------------
if "targets" not in st.session_state:
    st.session_state.targets = load_price_targets()

synced_symbols = load_synced_watchlist()
default_labels = [
    lbl for lbl in stock_list["label"].tolist()
    if lbl.split(" - ")[0] in synced_symbols
]

selected_labels = st.multiselect(
    "🔍 Search and select stocks to watch (type to search):",
    options=stock_list["label"].tolist(),
    default=default_labels,
)
selected_symbols = [label.split(" - ")[0] for label in selected_labels]

col_save1, col_save2 = st.columns([1, 3])
with col_save1:
    if st.button("💾 Save as Auto-Alert Watchlist"):
        if save_synced_watchlist(selected_symbols):
            st.success("Saved! The hourly checker will use this list from its next run.")
        else:
            st.error("Couldn't save. Check GITHUB_TOKEN/GITHUB_REPO secrets.")

# ----------------------------------------------------------------------
# Data fetching
# ----------------------------------------------------------------------
@st.cache_data(ttl=3600)
def get_stock_data(symbol):
    ticker = symbol + ".NS"
    return yf.download(ticker, period="5y", interval="1d", progress=False)


@st.cache_data(ttl=86400)
def get_sector_industry(symbol):
    return get_sector_industry_info(symbol)


@st.cache_data(ttl=1800)
def cached_news(query, max_items=4):
    return get_news_headlines(query, max_items=max_items)


# ----------------------------------------------------------------------
# Display each selected stock
# ----------------------------------------------------------------------
reports = []
stock_data_cache = {}

for symbol in selected_symbols:
    st.subheader(symbol)
    with st.spinner(f"Fetching data for {symbol}..."):
        df = get_stock_data(symbol)

    if df.empty:
        st.warning(f"No data found for {symbol}. Check the symbol is correct.")
        continue

    stock_data_cache[symbol] = df

    all_time_high = float(df["Close"].max())
    all_time_low = float(df["Close"].min())
    current_price = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2]) if len(df) > 1 else current_price
    daily_change_pct = (
        (current_price - prev_close) / prev_close * 100 if prev_close else 0.0
    )

    sector, industry = get_sector_industry(symbol)

    col1, col2 = st.columns([3, 1])
    with col1:
        st.line_chart(df["Close"])
    with col2:
        st.metric("Current Price", f"₹{current_price:.2f}", f"{daily_change_pct:+.2f}% today")
        st.metric("All-Time High", f"₹{all_time_high:.2f}")
        st.metric("All-Time Low", f"₹{all_time_low:.2f}")
        st.caption(f"Sector: {sector} | Industry: {industry}")

    feat_df = compute_features(df)
    pred, prob, latest_row = train_and_predict(feat_df)

    signal_text = "Not enough data"
    if pred is None:
        st.info("Not enough history yet for a prediction.")
    else:
        direction = "📈 UP" if pred == 1 else "📉 DOWN"
        label, color = confidence_label_and_color(prob)
        st.markdown(
            f"**AI Signal:** {direction} &nbsp; "
            f"<span style='background-color:{color};color:white;padding:2px 10px;"
            f"border-radius:6px;font-size:13px;'>{label} ({prob*100:.1f}%)</span>",
            unsafe_allow_html=True,
        )
        signal_text = f"{direction} ({label}, {prob*100:.1f}% confidence)"

        with st.expander("Why this signal?"):
            for reason in explain_signal(latest_row):
                st.write(f"- {reason}")

        accuracy = backtest_accuracy(feat_df)
        if accuracy is not None:
            st.caption(
                f"📊 On this stock's last 30 trading days, this type of model "
                f"was right about {accuracy:.0f}% of the time. This is a rough "
                f"guide, not a guarantee of future accuracy."
            )

    with st.expander(f"📰 Recent news about {symbol}"):
        headlines = cached_news(symbol_to_name.get(symbol, symbol) + " stock", max_items=4)
        if headlines:
            for h in headlines:
                if h.get("link"):
                    st.markdown(f"- [{h['title']}]({h['link']})")
                else:
                    st.write(f"- {h['title']}")
        else:
            st.write("No recent news found.")

    with st.expander(f"🎯 Set a price alert for {symbol}"):
        existing = st.session_state.targets.get(symbol, {})
        target_price = st.number_input(
            "Alert me when the price reaches:",
            min_value=0.0,
            value=float(existing.get("target", current_price)),
            step=1.0,
            key=f"target_{symbol}",
        )
        direction_choice = st.selectbox(
            "Direction:",
            ["Above", "Below"],
            index=0 if existing.get("direction", "above") == "above" else 1,
            key=f"direction_{symbol}",
        )
        if st.button(f"Save Alert for {symbol}", key=f"save_target_{symbol}"):
            st.session_state.targets[symbol] = {
                "target": target_price,
                "direction": direction_choice.lower(),
            }
            if save_price_targets(st.session_state.targets):
                st.success(f"Price alert saved for {symbol}.")
            else:
                st.error("Couldn't save. Check GITHUB_TOKEN/GITHUB_REPO secrets.")

    reports.append({
        "symbol": symbol,
        "high": all_time_high,
        "low": all_time_low,
        "signal": signal_text,
        "daily_change": daily_change_pct,
        "sector": sector,
    })

if not selected_symbols:
    st.info("👆 Search and select one or more stocks above to get started.")

# ----------------------------------------------------------------------
# Top movers today
# ----------------------------------------------------------------------
if reports:
    st.divider()
    st.header("🏆 Top Movers Today")
    movers_sorted = sorted(reports, key=lambda r: abs(r["daily_change"]), reverse=True)[:5]
    for r in movers_sorted:
        arrow = "📈" if r["daily_change"] >= 0 else "📉"
        st.write(f"{arrow} **{r['symbol']}**: {r['daily_change']:+.2f}% today")

# ----------------------------------------------------------------------
# Compare stocks side-by-side
# ----------------------------------------------------------------------
if len(selected_symbols) >= 2:
    st.divider()
    st.header("📊 Compare Stocks")
    compare_choices = st.multiselect(
        "Pick 2-3 stocks to compare (normalized % change from start):",
        options=selected_symbols,
        default=selected_symbols[: min(3, len(selected_symbols))],
        max_selections=3,
    )
    if len(compare_choices) >= 2:
        compare_df = pd.DataFrame()
        for sym in compare_choices:
            d = stock_data_cache.get(sym)
            if d is not None and not d.empty:
                compare_df[sym] = d["Close"] / d["Close"].iloc[0] * 100
        if not compare_df.empty:
            st.line_chart(compare_df)
            st.caption(
                "Each line starts at 100 and shows % change from there, so stocks "
                "with very different prices can be compared fairly on one chart."
            )

# ----------------------------------------------------------------------
# Alerts are fully automatic now (see checker.py, run hourly by GitHub
# Actions) - no manual "send report" button here anymore. The dashboard
# is for browsing/searching/setting alerts; the hourly checker is what
# actually emails/Telegrams you.
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# AI chat bot (with news context + voice input)
# ----------------------------------------------------------------------
st.divider()
st.header("🤖 Ask the AI Bot")

VOICE_HTML = """
<div>
  <button id="voice-btn" style="padding:8px 16px;border-radius:8px;border:none;
    background:#1DB954;color:white;font-size:14px;cursor:pointer;">
    🎤 Speak your question
  </button>
  <p id="voice-status" style="color:gray;font-size:12px;margin-top:6px;"></p>
</div>
<script>
const btn = document.getElementById('voice-btn');
const status = document.getElementById('voice-status');
btn.onclick = function() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    status.innerText = "Voice input isn't supported in this browser (try Chrome).";
    return;
  }
  const recognition = new SpeechRecognition();
  recognition.lang = 'en-IN';
  recognition.onresult = function(event) {
    const transcript = event.results[0][0].transcript;
    status.innerText = "Heard: " + transcript;
    const params = new URLSearchParams(window.parent.location.search);
    params.set('voice_text', transcript);
    window.parent.location.search = params.toString();
  };
  recognition.onerror = function(event) {
    status.innerText = "Error: " + event.error;
  };
  status.innerText = "Listening...";
  recognition.start();
};
</script>
"""
components.html(VOICE_HTML, height=90)
st.caption(
    "Voice input works best in Chrome (desktop or Android). Safari/iOS support "
    "is inconsistent — type your question there instead if it doesn't respond."
)

voice_text = st.query_params.get("voice_text", None)

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

typed_question = st.chat_input("Ask about your selected stocks...")

user_question = typed_question
if not user_question and voice_text:
    user_question = voice_text
    try:
        del st.query_params["voice_text"]
    except Exception:
        pass

if user_question:
    st.session_state.chat_history.append({"role": "user", "content": user_question})
    with st.chat_message("user"):
        st.write(user_question)

    context_lines = [
        f"{r['symbol']}: Signal = {r['signal']}, Sector = {r['sector']}, "
        f"Today's change = {r['daily_change']:+.2f}%, "
        f"All-Time High = ₹{r['high']:.2f}, All-Time Low = ₹{r['low']:.2f}"
        for r in reports
    ]
    context = "\n".join(context_lines) if context_lines else "No stocks selected yet."

    news_context_lines = []
    for r in reports:
        heads = cached_news(symbol_to_name.get(r["symbol"], r["symbol"]) + " stock", max_items=2)
        titles = "; ".join(h["title"] for h in heads if h.get("title"))
        if titles:
            news_context_lines.append(f"{r['symbol']} recent headlines: {titles}")
    if news_context_lines:
        context += "\n\nRecent news (titles only):\n" + "\n".join(news_context_lines)

    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel("gemini-1.5-flash")

        full_prompt = (
            "You are a helpful assistant discussing Indian stocks for an amateur investor. "
            "You are not a licensed financial advisor. Be clear that the signals are from a "
            "simple statistical model, not guarantees, and encourage the user to do their own "
            "research before acting. You may reference the news headlines below in general "
            "terms, but do not quote them verbatim.\n\n"
            f"Current data:\n{context}\n\n"
            f"User question: {user_question}"
        )

        response = model.generate_content(full_prompt)
        answer = response.text
    except Exception as e:
        answer = f"Sorry, I couldn't reach the AI bot right now ({e})."

    st.session_state.chat_history.append({"role": "assistant", "content": answer})
    with st.chat_message("assistant"):
        st.write(answer)
