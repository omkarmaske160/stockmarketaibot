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
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
        border-radius: 8px 8px 0 0;
    }
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
        return False, "GitHub sync isn't configured (missing GITHUB_TOKEN/GITHUB_REPO)."
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
        return False, "GitHub sync isn't configured (missing GITHUB_TOKEN/GITHUB_REPO)."
    content = json.dumps(targets_dict, indent=2)
    return github_sync.update_file(
        GITHUB_TOKEN, GITHUB_REPO, TARGETS_PATH, content,
        "Update price targets from dashboard"
    )


# ----------------------------------------------------------------------
# A much larger fallback stock list, used only if NSE's live list can't
# be fetched (e.g. temporary blocking of cloud-server requests).
# ----------------------------------------------------------------------
FALLBACK_STOCKS = {
    "SYMBOL": [
        "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "HINDUNILVR", "ITC",
        "SBIN", "BHARTIARTL", "BAJFINANCE", "LT", "KOTAKBANK", "AXISBANK",
        "ASIANPAINT", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "WIPRO",
        "NESTLEIND", "ONGC", "NTPC", "POWERGRID", "M&M", "TATAMOTORS",
        "TATASTEEL", "ADANIENT", "ADANIPORTS", "JSWSTEEL", "COALINDIA",
        "HCLTECH", "TECHM", "INDUSINDBK", "BAJAJFINSV", "DRREDDY", "CIPLA",
        "DIVISLAB", "GRASIM", "HEROMOTOCO", "BRITANNIA", "EICHERMOT", "BPCL",
        "HDFCLIFE", "SBILIFE", "SHREECEM", "UPL", "APOLLOHOSP", "BAJAJ-AUTO",
        "TATACONSUM", "HINDALCO", "VEDL", "PIDILITIND", "DLF", "GODREJCP",
        "DABUR", "HAVELLS", "SIEMENS", "PNB", "BANKBARODA", "CANBK", "IOC",
        "GAIL", "ZOMATO", "IRCTC", "TRENT", "LTIM", "AMBUJACEM", "ACC",
        "BOSCHLTD", "COLPAL", "MARICO", "PAGEIND", "PIIND", "SRF", "TORNTPHARM",
        "LUPIN", "AUROPHARMA", "BIOCON", "MOTHERSON", "TVSMOTOR", "BEL",
        "HAL", "IDEA", "YESBANK", "ZEEL", "INDIGO", "NAUKRI",
    ],
    "NAME OF COMPANY": [
        "Reliance Industries", "Tata Consultancy Services", "HDFC Bank",
        "ICICI Bank", "Infosys", "Hindustan Unilever", "ITC Ltd",
        "State Bank of India", "Bharti Airtel", "Bajaj Finance",
        "Larsen & Toubro", "Kotak Mahindra Bank", "Axis Bank",
        "Asian Paints", "Maruti Suzuki", "Sun Pharmaceutical", "Titan Company",
        "UltraTech Cement", "Wipro", "Nestle India", "Oil & Natural Gas Corp",
        "NTPC", "Power Grid Corp", "Mahindra & Mahindra", "Tata Motors",
        "Tata Steel", "Adani Enterprises", "Adani Ports", "JSW Steel",
        "Coal India", "HCL Technologies", "Tech Mahindra", "IndusInd Bank",
        "Bajaj Finserv", "Dr. Reddy's Labs", "Cipla", "Divi's Labs",
        "Grasim Industries", "Hero MotoCorp", "Britannia Industries",
        "Eicher Motors", "Bharat Petroleum", "HDFC Life Insurance",
        "SBI Life Insurance", "Shree Cement", "UPL Ltd", "Apollo Hospitals",
        "Bajaj Auto", "Tata Consumer Products", "Hindalco Industries",
        "Vedanta", "Pidilite Industries", "DLF Ltd", "Godrej Consumer Products",
        "Dabur India", "Havells India", "Siemens India", "Punjab National Bank",
        "Bank of Baroda", "Canara Bank", "Indian Oil Corp", "GAIL India",
        "Zomato", "IRCTC", "Trent Ltd", "LTIMindtree", "Ambuja Cements",
        "ACC Ltd", "Bosch Ltd", "Colgate-Palmolive India", "Marico",
        "Page Industries", "PI Industries", "SRF Ltd", "Torrent Pharma",
        "Lupin", "Aurobindo Pharma", "Biocon", "Samvardhana Motherson",
        "TVS Motor Company", "Bharat Electronics", "Hindustan Aeronautics",
        "Vodafone Idea", "Yes Bank", "Zee Entertainment", "IndiGo (InterGlobe Aviation)",
        "Info Edge (Naukri)",
    ],
}


@st.cache_data(ttl=86400)
def load_nse_stock_list():
    """
    Fetches the full official NSE equity list. NSE's servers block plain
    requests without a prior "real browser" style visit, so we first hit
    the homepage to pick up required cookies, then fetch the CSV using the
    same session. Falls back to a large built-in list if this fails.
    """
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        session.get("https://www.nseindia.com", timeout=10)  # sets required cookies
        resp = session.get(
            "https://archives.nseindia.com/content/equity/EQUITY_L.csv", timeout=10
        )
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]
        df = df[["SYMBOL", "NAME OF COMPANY"]].dropna()
        if len(df) < 200:
            raise ValueError("NSE list looked incomplete, using fallback instead")
        return df, True
    except Exception:
        return pd.DataFrame(FALLBACK_STOCKS), False


stock_list, using_live_nse_list = load_nse_stock_list()
stock_list["label"] = stock_list["SYMBOL"] + " - " + stock_list["NAME OF COMPANY"]
symbol_to_name = dict(zip(stock_list["SYMBOL"], stock_list["NAME OF COMPANY"]))

st.title("📈 Indian Stock Market AI Dashboard")
st.caption(
    "Search NSE stocks, watch multiple at once, compare them, get AI signals "
    "with explanations and accuracy history, set price alerts, and ask the bot."
)

if not using_live_nse_list:
    st.info(
        f"Using a built-in list of {len(stock_list)} major NSE stocks right now "
        "(NSE's live list couldn't be reached from this server). Search should "
        "still cover all the most commonly traded stocks."
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
        ok, err = save_synced_watchlist(selected_symbols)
        if ok:
            st.success("Saved! The hourly checker will use this list from its next run.")
        else:
            st.error(f"Couldn't save: {err}")

# ----------------------------------------------------------------------
# Data fetching (robust against MultiIndex columns from yfinance)
# ----------------------------------------------------------------------
@st.cache_data(ttl=3600)
def get_stock_data(symbol):
    ticker = symbol + ".NS"
    df = yf.download(ticker, period="5y", interval="1d", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


@st.cache_data(ttl=86400)
def get_sector_industry(symbol):
    return get_sector_industry_info(symbol)


@st.cache_data(ttl=1800)
def cached_news(query, max_items=4):
    return get_news_headlines(query, max_items=max_items)


@st.cache_data(ttl=3600)
def get_working_gemini_model(api_key):
    """
    Google occasionally retires specific model version names. Rather than
    hardcode one that can go stale, ask the API what's actually available
    on this key and use the first model that supports chat-style generation.
    """
    try:
        genai.configure(api_key=api_key)
        for m in genai.list_models():
            methods = getattr(m, "supported_generation_methods", [])
            if "generateContent" in methods:
                return m.name
    except Exception:
        pass
    return "gemini-1.5-flash"  # last-resort guess if listing itself fails


# ----------------------------------------------------------------------
# Compute everything for each selected stock FIRST (no rendering yet), so
# we can show a summary bar before the detailed per-stock cards.
# ----------------------------------------------------------------------
stock_data = []
stock_data_cache = {}

for symbol in selected_symbols:
    df = get_stock_data(symbol)
    if df.empty:
        stock_data.append({"symbol": symbol, "error": "No data found for this symbol."})
        continue

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if close.empty:
        stock_data.append({"symbol": symbol, "error": "No valid closing-price data found."})
        continue

    stock_data_cache[symbol] = df

    all_time_high = float(close.max())
    all_time_low = float(close.min())
    current_price = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) > 1 else current_price
    daily_change_pct = (
        (current_price - prev_close) / prev_close * 100 if prev_close else 0.0
    )

    sector, industry = get_sector_industry(symbol)

    feat_df = compute_features(df)
    pred, prob, latest_row = train_and_predict(feat_df)

    signal_text = "Not enough data"
    reasons = []
    accuracy = None
    label, color = "Unknown", "#888888"
    if pred is not None:
        direction = "UP" if pred == 1 else "DOWN"
        label, color = confidence_label_and_color(prob)
        signal_text = f"{direction} ({label}, {prob*100:.1f}% confidence)"
        reasons = explain_signal(latest_row)
        accuracy = backtest_accuracy(feat_df)

    stock_data.append({
        "symbol": symbol,
        "error": None,
        "df": df,
        "high": all_time_high,
        "low": all_time_low,
        "current_price": current_price,
        "daily_change": daily_change_pct,
        "sector": sector,
        "industry": industry,
        "pred": pred,
        "prob": prob,
        "label": label,
        "color": color,
        "signal_text": signal_text,
        "reasons": reasons,
        "accuracy": accuracy,
    })

reports = [s for s in stock_data if not s.get("error")]

# ----------------------------------------------------------------------
# Summary bar
# ----------------------------------------------------------------------
if reports:
    up_count = sum(1 for r in reports if r["pred"] == 1)
    down_count = sum(1 for r in reports if r["pred"] == 0)
    avg_conf = np.mean([r["prob"] for r in reports if r["prob"] is not None]) * 100 \
        if any(r["prob"] is not None for r in reports) else 0

    st.divider()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Stocks Watched", len(reports))
    k2.metric("📈 Bullish Signals", up_count)
    k3.metric("📉 Bearish Signals", down_count)
    k4.metric("Avg. Confidence", f"{avg_conf:.0f}%")
    st.divider()
elif not selected_symbols:
    st.info("👆 Search and select one or more stocks above to get started.")

# ----------------------------------------------------------------------
# Tabbed layout
# ----------------------------------------------------------------------
tab_watchlist, tab_movers, tab_chat = st.tabs(
    ["📊 Watchlist", "🏆 Movers & Compare", "🤖 AI Chat Bot"]
)

# ---- Tab 1: Watchlist ----
with tab_watchlist:
    for item in stock_data:
        symbol = item["symbol"]
        if item.get("error"):
            st.warning(f"{symbol}: {item['error']}")
            continue

        with st.container(border=True):
            st.subheader(symbol)
            col1, col2 = st.columns([3, 1])
            with col1:
                st.line_chart(item["df"]["Close"])
            with col2:
                st.metric(
                    "Current Price",
                    f"₹{item['current_price']:.2f}",
                    f"{item['daily_change']:+.2f}% today",
                )
                st.metric("All-Time High", f"₹{item['high']:.2f}")
                st.metric("All-Time Low", f"₹{item['low']:.2f}")
                st.caption(f"Sector: {item['sector']} | Industry: {item['industry']}")

            if item["pred"] is None:
                st.info("Not enough history yet for a prediction.")
            else:
                direction = "📈 UP" if item["pred"] == 1 else "📉 DOWN"
                badge_color = item["color"]
                badge_label = item["label"]
                badge_prob = item["prob"] * 100
                st.markdown(
                    f"**AI Signal:** {direction} &nbsp; "
                    f"<span style='background-color:{badge_color};color:white;"
                    f"padding:2px 10px;border-radius:6px;font-size:13px;'>"
                    f"{badge_label} ({badge_prob:.1f}%)</span>",
                    unsafe_allow_html=True,
                )
                st.progress(min(max(item["prob"], 0.0), 1.0))

                with st.expander("Why this signal?"):
                    for reason in item["reasons"]:
                        st.write(f"- {reason}")

                if item["accuracy"] is not None:
                    st.caption(
                        f"📊 On this stock's last 30 trading days, this type of "
                        f"model was right about {item['accuracy']:.0f}% of the "
                        f"time. This is a rough guide, not a guarantee."
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
                    value=float(existing.get("target", item["current_price"])),
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
                    ok, err = save_price_targets(st.session_state.targets)
                    if ok:
                        st.success(f"Price alert saved for {symbol}.")
                    else:
                        st.error(f"Couldn't save: {err}")

# ---- Tab 2: Movers & Compare ----
with tab_movers:
    if reports:
        st.header("🏆 Top Movers Today")
        movers_sorted = sorted(reports, key=lambda r: abs(r["daily_change"]), reverse=True)[:5]
        for r in movers_sorted:
            arrow = "📈" if r["daily_change"] >= 0 else "📉"
            st.write(f"{arrow} **{r['symbol']}**: {r['daily_change']:+.2f}% today")
    else:
        st.info("Select stocks in the Watchlist tab to see today's movers here.")

    if len(selected_symbols) >= 2:
        st.divider()
        st.header("📊 Compare Stocks")
        compare_choices = st.multiselect(
            "Pick 2-3 stocks to compare (normalized % change from start):",
            options=selected_symbols,
            default=selected_symbols[: min(3, len(selected_symbols))],
            max_selections=3,
            key="compare_multiselect",
        )
        if len(compare_choices) >= 2:
            compare_df = pd.DataFrame()
            for sym in compare_choices:
                d = stock_data_cache.get(sym)
                if d is not None and not d.empty:
                    c = pd.to_numeric(d["Close"], errors="coerce").dropna()
                    if not c.empty:
                        compare_df[sym] = c / c.iloc[0] * 100
            if not compare_df.empty:
                st.line_chart(compare_df)
                st.caption(
                    "Each line starts at 100 and shows % change from there, so "
                    "stocks with very different prices can be compared fairly."
                )
    elif reports:
        st.info("Select 2 or more stocks in the Watchlist tab to compare them here.")

# ---- Tab 3: AI Chat Bot ----
with tab_chat:
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
        "Voice input works best in Chrome (desktop or Android). Safari/iOS "
        "support is inconsistent — type your question there instead if it "
        "doesn't respond."
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
            f"{r['symbol']}: Signal = {r['signal_text']}, Sector = {r['sector']}, "
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
            model_name = get_working_gemini_model(st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel(model_name)

            full_prompt = (
                "You are a helpful assistant discussing Indian stocks for an "
                "amateur investor. You are not a licensed financial advisor. "
                "Be clear that the signals are from a simple statistical model, "
                "not guarantees, and encourage the user to do their own research "
                "before acting. You may reference the news headlines below in "
                "general terms, but do not quote them verbatim.\n\n"
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
