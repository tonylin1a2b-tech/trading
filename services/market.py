# services/market.py — 行情資料抓取（Yahoo Finance / TWSE / FinMind）

import datetime
import requests
import pandas as pd
import streamlit as st

from utils.http import yf_chart, safe_request
from config import MARKET_HEADERS, TTL_DAILY, TTL_INTRADAY, TTL_KLINE


@st.cache_data(ttl=TTL_INTRADAY)
def fetch_taiex_history(range_: str = "6mo") -> pd.DataFrame:
    """抓取加權指數（^TWII）日線收盤價"""
    try:
        result = yf_chart("%5ETWII", interval="1d", range_=range_)
        if result is None:
            return pd.DataFrame()
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        df = pd.DataFrame({
            "date": pd.to_datetime([datetime.datetime.fromtimestamp(t) for t in timestamps]),
            "close": closes,
        })
        return df.dropna().sort_values("date").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=TTL_INTRADAY)
def fetch_fedfunds_futures(range_: str = "10d") -> pd.DataFrame:
    """抓取 30天聯邦基金利率期貨（ZQ=F），用於推算升降息預期"""
    try:
        result = yf_chart("ZQ%3DF", interval="1d", range_=range_)
        if result is None:
            return pd.DataFrame()
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        df = pd.DataFrame({
            "date": pd.to_datetime([datetime.datetime.fromtimestamp(t) for t in timestamps]),
            "close": closes,
        })
        return df.dropna().sort_values("date").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=TTL_KLINE)
def fetch_stock_kline(stock_id: str, interval: str = "1d", range_: str = "6mo") -> pd.DataFrame:
    """個股 K 棒資料（含成交量），上市 .TW / 上櫃 .TWO 自動 fallback"""
    for suffix in (".TW", ".TWO"):
        try:
            result = yf_chart(f"{stock_id}{suffix}", interval=interval, range_=range_)
            if result is None:
                continue
            timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]
            df = pd.DataFrame({
                "date": pd.to_datetime([datetime.datetime.fromtimestamp(t) for t in timestamps]),
                "open": quote["open"],
                "high": quote["high"],
                "low": quote["low"],
                "close": quote["close"],
                "volume": quote.get("volume", [None] * len(timestamps)),
            })
            df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
            if not df.empty:
                return df
        except Exception:
            continue
    return pd.DataFrame()


@st.cache_data(ttl=TTL_DAILY)
def fetch_sector_changes(sectors: dict) -> dict:
    """傳入 {名稱: Yahoo ticker}，回傳 {名稱: 當日漲跌%}"""

    def _try_tickers(ticker: str):
        base = ticker
        for sfx in (".TWO", ".TW"):
            if ticker.endswith(sfx):
                base = ticker[: -len(sfx)]
                break
        if base.isdigit():
            candidates = [base + ".TW", base + ".TWO"]
            if ticker not in candidates:
                candidates.insert(0, ticker)
        else:
            candidates = [ticker]
        return candidates

    result: dict = {}
    for name, ticker in sectors.items():
        for t in _try_tickers(ticker):
            try:
                chart = yf_chart(t, interval="1d", range_="10d")
                if chart is None:
                    continue
                closes = [c for c in chart["indicators"]["quote"][0]["close"] if c is not None]
                if len(closes) >= 2:
                    result[name] = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)
                    break
            except Exception:
                continue
    return result


@st.cache_data(ttl=30 * 60)
def fetch_nested_changes(flat_tickers: tuple) -> dict:
    """接收 ((名稱, ticker), ...) tuple，回傳 {名稱: (price, chg%)}"""

    def _fetch_closes(ticker: str):
        chart = yf_chart(ticker, interval="1d", range_="10d")
        if chart is None:
            return None
        closes = [c for c in chart["indicators"]["quote"][0]["close"] if c is not None]
        return closes if len(closes) >= 2 else None

    def _auto_ticker(ticker: str):
        if ticker.endswith(".TW"):
            return [ticker, ticker[:-3] + ".TWO"]
        elif ticker.endswith(".TWO"):
            return [ticker, ticker[:-4] + ".TW"]
        return [ticker]

    result: dict = {}
    for name, ticker in flat_tickers:
        closes = None
        for t in _auto_ticker(ticker):
            try:
                closes = _fetch_closes(t)
                if closes:
                    break
            except Exception:
                continue
        if closes:
            price = closes[-1]
            chg = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)
            result[name] = (round(price, 2), chg)
    return result


@st.cache_data(ttl=TTL_DAILY * 6)
def fetch_breadth_signal(top_n: int = 100, _api_token: str = "") -> dict:
    """成交值前 top_n 檔個股中，5日均 > 20日均（多頭排列）的統計"""
    from FinMind.data import DataLoader
    api = DataLoader()
    api.login_by_token(api_token=_api_token)

    stock_info = api.taiwan_stock_info()
    stock_info = stock_info[~stock_info["industry_category"].str.contains("ETF|基金", na=False)]
    stock_info = stock_info[stock_info["stock_id"].str.match(r"^\d{4}$")]
    valid_stocks = set(stock_info["stock_id"].tolist())

    url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json"
    res = requests.get(url, timeout=15)
    data = res.json()
    df = pd.DataFrame(data["data"], columns=data["fields"])
    df = df[df["證券代號"].isin(valid_stocks)]
    df["成交金額"] = df["成交金額"].str.replace(",", "").astype(float)
    topN = df.sort_values("成交金額", ascending=False).head(top_n)
    stock_ids = topN["證券代號"].tolist()

    end_date = datetime.date.today().strftime("%Y-%m-%d")
    start_date = (datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")

    golden, dead = 0, 0
    for sid in stock_ids:
        try:
            price = api.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=end_date)
            if len(price) >= 20:
                price = price.sort_values("date")
                ma5 = price["close"].iloc[-5:].mean()
                ma20 = price["close"].iloc[-20:].mean()
                if ma5 > ma20:
                    golden += 1
                else:
                    dead += 1
        except Exception:
            pass

    return {"golden": golden, "dead": dead, "valid": golden + dead, "total": len(stock_ids)}


def compute_support_resistance(df_k: pd.DataFrame) -> list:
    """從 K 棒找結構性支撐／壓力，回傳 [(price, label, type), ...]"""
    if len(df_k) < 10:
        return []

    close, high, low = df_k["close"], df_k["high"], df_k["low"]
    current = close.iloc[-1]
    res_candidates, sup_candidates = [], []
    window = 3

    for i in range(window, len(df_k) - window):
        before_high = high.iloc[i - window:i].max()
        after_high  = high.iloc[i + 1:i + window + 1].max()
        before_low  = low.iloc[i - window:i].min()
        after_low   = low.iloc[i + 1:i + window + 1].min()

        if high.iloc[i] > before_high and high.iloc[i] > after_high and high.iloc[i] > current:
            res_candidates.append((high.iloc[i], "結構性壓力(山頂)"))
        if low.iloc[i] < before_low and low.iloc[i] < after_low and low.iloc[i] < current:
            sup_candidates.append((low.iloc[i], "結構性支撐(山谷)"))

    levels = []
    if res_candidates:
        price, label = min(res_candidates, key=lambda x: x[0] - current)
        levels.append((price, label, "resistance"))
    if sup_candidates:
        price, label = min(sup_candidates, key=lambda x: current - x[0])
        levels.append((price, label, "support"))

    return levels


def check_stock_alerts(df_k: pd.DataFrame) -> list:
    """最新 K 棒是否觸發成交量異常或支撐/壓力提醒"""
    alerts = []
    if len(df_k) < 6:
        return alerts

    volume = df_k["volume"]
    latest_vol = volume.iloc[-1]
    avg5 = volume.iloc[-6:-1].mean()
    if pd.notna(latest_vol) and avg5 > 0 and latest_vol > 1.5 * avg5:
        alerts.append("🔥 成交量異常放大")

    latest_high = df_k["high"].iloc[-1]
    latest_low  = df_k["low"].iloc[-1]
    for level_price, _, ltype in compute_support_resistance(df_k):
        if ltype == "resistance" and latest_high >= level_price:
            alerts.append(f"⚠️ 觸及壓力 {level_price:.2f}")
        if ltype == "support" and latest_low <= level_price:
            alerts.append(f"⚠️ 觸及支撐 {level_price:.2f}")

    return alerts
