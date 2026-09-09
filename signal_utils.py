"""
Shared logic between the dashboard (app.py) and the hourly checker
(checker.py), so both always agree on how signals are computed and
explained.
"""

from sklearn.ensemble import RandomForestClassifier

FEATURES = ["SMA10", "SMA50", "Return", "Volatility", "RSI"]


def compute_features(df):
    df = df.copy()
    df["SMA10"] = df["Close"].rolling(10).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["Return"] = df["Close"].pct_change()
    df["Volatility"] = df["Return"].rolling(10).std()
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    df["RSI"] = 100 - (100 / (1 + rs))
    df["Target"] = (df["Close"].shift(-1) > df["Close"]).astype(int)
    return df.dropna()


def train_and_predict(df):
    """Returns (prediction, confidence, latest_feature_row) or (None, None, None)."""
    X = df[FEATURES][:-1]
    y = df["Target"][:-1]
    if len(X) < 50:
        return None, None, None
    model = RandomForestClassifier(n_estimators=200, random_state=42)
    model.fit(X, y)
    latest = df[FEATURES].iloc[[-1]]
    pred = model.predict(latest)[0]
    prob = model.predict_proba(latest)[0][pred]
    return pred, prob, latest.iloc[0]


def explain_signal(latest_row):
    """Return a short list of plain-English reasons behind the current signal."""
    reasons = []
    sma10 = latest_row["SMA10"]
    sma50 = latest_row["SMA50"]
    rsi = latest_row["RSI"]
    ret = latest_row["Return"]
    vol = latest_row["Volatility"]

    if sma10 > sma50:
        reasons.append("Short-term average is above the long-term average (uptrend)")
    else:
        reasons.append("Short-term average is below the long-term average (downtrend)")

    if rsi >= 70:
        reasons.append(f"RSI is high at {rsi:.0f} (overbought - possible pullback risk)")
    elif rsi <= 30:
        reasons.append(f"RSI is low at {rsi:.0f} (oversold - possible rebound potential)")
    else:
        reasons.append(f"RSI is neutral at {rsi:.0f}")

    if ret > 0:
        reasons.append(f"Price rose {ret*100:.2f}% in the most recent session")
    else:
        reasons.append(f"Price fell {ret*100:.2f}% in the most recent session")

    if vol is not None and vol > 0.02:
        reasons.append("Recent volatility is relatively high, so swings could be larger than usual")

    return reasons


def confidence_label_and_color(prob):
    """Maps a model confidence (0-1) to a plain label and a display color."""
    pct = prob * 100
    if pct >= 75:
        return "Strong", "#2ecc71"   # green
    elif pct >= 60:
        return "Moderate", "#f1c40f"  # yellow
    else:
        return "Weak", "#e74c3c"     # red


def backtest_accuracy(feat_df, window=30):
    """
    Lightweight historical accuracy check: trains one model on all data
    except the most recent `window` days, then checks how many of those
    `window` days it would have predicted correctly.

    This is a fast approximation for display purposes, NOT a rigorous
    walk-forward backtest (which would retrain daily) - treat the result
    as a rough guide to how reliable this stock's signals have been
    recently, not a guarantee of future performance.
    """
    if len(feat_df) < window + 60:
        return None

    train_df = feat_df.iloc[:-window]
    test_df = feat_df.iloc[-window:]

    X_train = train_df[FEATURES][:-1]
    y_train = train_df["Target"][:-1]
    if len(X_train) < 50:
        return None

    model = RandomForestClassifier(n_estimators=200, random_state=42)
    model.fit(X_train, y_train)

    X_test = test_df[FEATURES]
    y_test = test_df["Target"]
    preds = model.predict(X_test)
    accuracy = (preds == y_test.values).mean() * 100
    return accuracy
