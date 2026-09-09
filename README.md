# Indian Stock AI Dashboard — Final Setup Guide (Cloud Hosted)

This gives you a free, always-online dashboard where you can search and
select any NSE-listed stock, see its chart with all-time high/low, get an
AI up/down signal, ask a chat bot questions, and automatically get an
emailed report every hour — all without your PC needing to be on.

You do **not** need to write or understand the code. Just follow these
steps and copy/paste where indicated.

---

## What you'll create (all free)

| Account | What it's for |
|---|---|
| GitHub | Stores the code; runs the free hourly automatic checker |
| Streamlit Community Cloud | Hosts the dashboard so you get a live web link, reachable from anywhere |
| Gmail App Password | Lets the app send you email reports |
| Google Gemini API key | Powers the chat bot (free) |

Total setup time: about 20 minutes, one time only.

---

## Step 1 — Create a GitHub repository

1. Go to https://github.com and sign up (free).
2. Click **+ → New repository**. Name it e.g. `stock-ai-dashboard`. Keep it
   **Public**. Click **Create repository**.
3. Click **Add file → Upload files** and upload everything, keeping the
   folder structure exactly as given:
   - `app.py`
   - `requirements.txt`
   - `checker.py`
   - `watchlist.txt`
   - `README.md`
   - `.gitignore`
   - `.streamlit/config.toml`
   - `.github/workflows/hourly_check.yml`
4. Click **Commit changes**.

---

## Step 2 — Get a Gmail App Password

1. Go to your Google Account → **Security**.
2. Turn on **2-Step Verification** if it isn't already on.
3. Search **"App Passwords"** in account settings, create one (name it
   "Stock Dashboard"), and copy the 16-character code shown.

---

## Step 3 — Get a free Google Gemini API key

1. Go to https://aistudio.google.com/apikey (sign in with any Google account).
2. Click **"Create API key"**, copy it.
3. This is completely free within Google's generous daily limit — no
   billing needed for personal use like this.

---

## Step 4 — Deploy the dashboard on Streamlit Community Cloud

1. Go to https://share.streamlit.io, sign in with GitHub.
2. Click **New app**, choose your repository, branch `main`, main file
   `app.py`.
3. Click **Advanced settings → Secrets** and paste:

   ```
   GMAIL_ADDRESS = "youremail@gmail.com"
   GMAIL_APP_PASSWORD = "your 16-character app password"
   RECEIVER_EMAIL = "youremail@gmail.com"
   GEMINI_API_KEY = "your-gemini-key-here"
   ```

4. Click **Deploy**. In a minute or two you'll get a public link like
   `https://yourname-stock-ai-dashboard.streamlit.app`.

*Note: free-tier apps "sleep" after a period of no visitors and take
~20–30 seconds to wake up on the next visit — normal, not a bug.*

---

## Step 5 — Add secrets for the automatic hourly emailer

1. In your GitHub repo: **Settings → Secrets and variables → Actions →
   New repository secret**.
2. Add these three (same values as Step 4, but GitHub Actions needs its
   own separate copy):
   - `GMAIL_ADDRESS`
   - `GMAIL_APP_PASSWORD`
   - `RECEIVER_EMAIL`

---

## Step 5.5 — Enable dashboard ↔ hourly-checker syncing (new)

This lets the stocks you select and the price alerts you set **on the
dashboard** automatically update what the hourly checker watches — no more
manually editing `watchlist.txt`.

1. On GitHub, go to your profile picture → **Settings → Developer settings
   → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Give it a name (e.g. "stock-dashboard-sync"), set expiration as you like,
   and under **Repository access**, choose **"Only select repositories"**
   and pick your `stock-ai-dashboard` repo.
3. Under **Permissions → Repository permissions**, find **"Contents"** and
   set it to **"Read and write"**.
4. Click **Generate token** and copy it immediately (starts with
   `github_pat_`) — you won't see it again.
5. Go back to your Streamlit app → **Settings → Secrets**, and add two more
   lines:
   ```
   GITHUB_TOKEN = "github_pat_..."
   GITHUB_REPO = "yourusername/stock-ai-dashboard"
   ```
6. Save. Your dashboard can now write directly to `watchlist.txt` and
   `price_targets.json` in your repo whenever you click the save buttons.

If you skip this step, the dashboard still works fully for manual use —
you'll just see a small notice that saving/syncing isn't available, and
you'd go back to editing `watchlist.txt` by hand as before.

---

## Step 5.6 — Set up Telegram alerts (optional, in addition to email)

Telegram delivers faster than email and feels more like a live notification.

1. In Telegram, search for **"BotFather"** and start a chat with it.
2. Send `/newbot`, give it a name and a username (must end in "bot", e.g.
   `myStockAlertsBot`). BotFather replies with a token — copy it.
3. Search for your new bot by its username and send it any message (e.g.
   "hi") — this is required so it's allowed to message you back.
4. In your browser, go to:
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   (replace `<YOUR_TOKEN>` with your actual token). Look for `"chat":{"id":`
   in the response — that number is your chat ID.
5. Add both to your **Streamlit secrets** (Step 4) and your **GitHub Actions
   secrets** (Step 5):
   ```
   TELEGRAM_BOT_TOKEN = "123456:ABC-your-token"
   TELEGRAM_CHAT_ID = "123456789"
   ```
6. That's it — the hourly checker will now message you on Telegram as
   well as email, automatically, every run.

If you skip this, everything still works via email only.

---

## Step 6 — Set your automatic watchlist

1. Open `watchlist.txt` in GitHub and list the NSE symbols you want
   auto-checked every hour, one per line (e.g. `RELIANCE`, `TCS`, `INFY`).
   **If you completed Step 5.5**, you can skip this — just select stocks on
   the dashboard and click "💾 Save as Auto-Alert Watchlist" instead.
2. To test immediately instead of waiting for the next scheduled hour: go
   to the **Actions** tab → **"Hourly Stock Check"** → **"Run workflow"**.
   Check your email a minute later.
3. The scheduled job runs automatically every hour, roughly 9:30am–3:30pm
   IST, Monday–Friday (Indian market hours). It emails you a full report,
   flagging any stock at the top that moved 2% or more in the last hour.
4. To change alert sensitivity, edit this line near the top of
   `checker.py`:
   ```python
   BIG_MOVE_THRESHOLD = 2.0  # percent move in the last hour to flag
   ```

---

## Step 7 — Install it as an app icon on your phone

**Android (Chrome):** open your dashboard link → tap **⋮** menu → **"Add
to Home screen"** → confirm.

**iPhone (Safari):** open your dashboard link → tap the **Share** icon →
scroll down → **"Add to Home Screen"** → confirm.

Either way, you now have a real icon on your home screen that opens the
dashboard full-screen, no browser bar, reachable from anywhere with an
internet connection — no PC or specific Wi-Fi required.

**Note on alerts:** the dashboard itself is for browsing and setting things
up (search, compare, set price targets, ask the bot) — it does not have a
manual "send report" button. All alerts (hourly reports, big movers, price
targets hit) are sent automatically by the hourly checker in the
background, so you never have to remember to check anything yourself.

---

## What's new in this version

- **Explanations**: each stock's signal has a "Why this signal?" expander.
- **Confidence color coding**: green (strong), yellow (moderate), red (weak).
- **Historical accuracy**: a rough "how often was this model right on this
  stock recently" indicator under each signal.
- **Price-target alerts**: set a target price and direction per stock; the
  hourly checker emails/Telegrams you when it's crossed.
- **Watchlist syncing**: with Step 5.5 set up, dashboard selections and
  price targets save directly into the repo — no manual file editing.
- **Compare stocks**: pick 2-3 of your selected stocks to see on one
  normalized chart.
- **Sector/industry info**: shown under each stock's metrics.
- **Top movers today**: a section ranking your selected stocks by how much
  they've moved today.
- **Telegram alerts**: optional, alongside email, set up in Step 5.6.
- **Live news headlines**: an expander per stock with recent headlines
  (via Google News, no API key needed), also fed to the chat bot as context.
- **Voice input**: a "🎤 Speak your question" button for the chat bot,
  using your browser's built-in speech recognition (works best in Chrome).

## Notes & honest caveats

- The "AI signal" is a simple statistical model trained on each stock's own
  price history. It's a rough, probabilistic lean — not a guarantee. Treat
  it as one input among many, not investment advice.
- The dashboard's search box pulls the live NSE stock list daily; if NSE's
  site is briefly unreachable, a small fallback list of major stocks is
  used instead.
- The hourly checker and the dashboard's search/select are two separate
  lists **unless you've set up Step 5.5 (GitHub sync)** — with that
  enabled, they stay in sync automatically. Without it, you'd edit
  `watchlist.txt` directly in GitHub as before.
- The "historical accuracy" figure trains one model on older data and
  tests it on the most recent 30 days — it's a fast approximation, not a
  full day-by-day walk-forward backtest. Treat it as a rough guide.
- Sector/industry lookups and news headlines depend on external free
  sources (Yahoo Finance, Google News) and may occasionally be slow, empty,
  or briefly unavailable — the app is written to fail gracefully in that case.
- Voice input relies on your browser's built-in speech recognition. It
  works well in Chrome (desktop and Android); Safari/iOS support is
  inconsistent — just type instead if the mic button doesn't respond.
