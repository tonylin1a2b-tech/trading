# services/macro.py — 總經資料抓取（Fed 利率、日銀、匯率、行事曆、資金水位）

import datetime
import pandas as pd
import streamlit as st

from utils.http import yf_chart, safe_request
from config import TTL_INTRADAY, TTL_CALENDAR

def _fred_key() -> str:
    """從 st.secrets 讀取 FRED API Key（免費申請：fred.stlouisfed.org/docs/api/api_key.html）"""
    try:
        return st.secrets.get("FRED_API_KEY", "")
    except Exception:
        return ""


def _fred(series_id: str, limit: int = 90) -> pd.DataFrame:
    """抓取 FRED 單一系列最新 N 筆，回傳 date/value DataFrame。"""
    key = _fred_key()
    if not key:
        return pd.DataFrame()
    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={key}&file_type=json"
        f"&sort_order=desc&limit={limit}"
    )
    res = safe_request(url)
    if res is None:
        return pd.DataFrame()
    try:
        obs = res.json().get("observations", [])
        df = pd.DataFrame(obs)[["date", "value"]]
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        return df.dropna().sort_values("date")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=TTL_INTRADAY)
def get_fed_probability(current_rate: float = 4.25) -> list:
    """抓取 Fed 期貨隱含利率，計算各會議日升降息預期"""
    meetings = {
        "2026-07-30": "ZQN26.CBT",
        "2026-09-17": "ZQU26.CBT",
        "2026-11-05": "ZQX26.CBT",
    }
    result = []
    for date, symbol in meetings.items():
        try:
            chart = yf_chart(symbol, interval="1d", range_="1d")
            if chart is None:
                continue
            price = chart["meta"]["regularMarketPrice"]
            implied_rate = round(100 - price, 4)
            diff = implied_rate - current_rate
            cuts = round(abs(diff) / 0.25, 1)
            if diff < -0.12:
                direction = "⬇️ 降息"
            elif diff > 0.12:
                direction = "⬆️ 升息"
            else:
                direction = "➡️ 不變"
            result.append({
                "Fed 會議日期": date,
                "期貨價格": price,
                "隱含利率": f"{implied_rate}%",
                "與現在利差": f"{round(diff, 4)}%",
                "預期降息碼數": f"{cuts} 碼",
                "方向": direction,
            })
        except Exception:
            continue
    return result


@st.cache_data(ttl=TTL_INTRADAY)
def get_history(symbol: str, label: str) -> pd.DataFrame:
    """抓取 Fed 期貨近3個月隱含利率趨勢（100 - 收盤價）"""
    try:
        chart = yf_chart(symbol, interval="1d", range_="3mo")
        if chart is None:
            return pd.DataFrame()
        timestamps = chart["timestamp"]
        closes = chart["indicators"]["quote"][0]["close"]
        df = pd.DataFrame({
            "date": pd.to_datetime([datetime.datetime.fromtimestamp(t) for t in timestamps]),
            label: [round(100 - c, 4) if c else None for c in closes],
        })
        return df.dropna().sort_values("date")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=TTL_INTRADAY)
def get_boj_history() -> pd.DataFrame:
    """日本公債 ETF（2621.T）近3個月走勢，作為日銀政策方向代理指標"""
    try:
        chart = yf_chart("2621.T", interval="1d", range_="3mo")
        if chart is None:
            return pd.DataFrame()
        timestamps = chart["timestamp"]
        closes = chart["indicators"]["quote"][0]["close"]
        df = pd.DataFrame({
            "date": pd.to_datetime([datetime.datetime.fromtimestamp(t) for t in timestamps]),
            "JGB_ETF": closes,
        })
        df = df[df["JGB_ETF"].notna() & (df["JGB_ETF"] > 0)]
        return df.sort_values("date")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=TTL_INTRADAY)
def get_dxy_history() -> pd.DataFrame:
    """美元指數（DX-Y.NYB）近3個月日線"""
    try:
        chart = yf_chart("DX-Y.NYB", interval="1d", range_="3mo")
        if chart is None:
            return pd.DataFrame()
        timestamps = chart["timestamp"]
        closes = chart["indicators"]["quote"][0]["close"]
        df = pd.DataFrame({
            "date": pd.to_datetime([datetime.datetime.fromtimestamp(t) for t in timestamps]),
            "DXY": closes,
        })
        return df.dropna().sort_values("date")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=TTL_INTRADAY)
def get_usdjpy_history() -> pd.DataFrame:
    """USD/JPY（JPY=X）近3個月日線"""
    try:
        chart = yf_chart("JPY=X", interval="1d", range_="3mo")
        if chart is None:
            return pd.DataFrame()
        timestamps = chart["timestamp"]
        closes = chart["indicators"]["quote"][0]["close"]
        df = pd.DataFrame({
            "date": pd.to_datetime([datetime.datetime.fromtimestamp(t) for t in timestamps]),
            "USDJPY": closes,
        })
        return df.dropna().sort_values("date")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=TTL_CALENDAR)
def get_calendar() -> pd.DataFrame:
    """本週高中影響力總經行事曆（Forex Factory）"""
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
    res = safe_request(url, headers=headers)
    if res is None:
        return pd.DataFrame()
    try:
        events = res.json()
    except Exception:
        return pd.DataFrame()
    country_translate = {
        "USD": "🇺🇸 美元", "JPY": "🇯🇵 日圓", "EUR": "🇪🇺 歐元",
        "GBP": "🇬🇧 英鎊", "AUD": "🇦🇺 澳幣", "CAD": "🇨🇦 加幣",
        "NZD": "🇳🇿 紐幣", "CHF": "🇨🇭 瑞郎",
    }
    df_cal = pd.DataFrame(events)
    if df_cal.empty:
        return df_cal
    df_cal["date"] = pd.to_datetime(df_cal["date"]).dt.tz_convert("Asia/Taipei")
    df_cal["時間"] = df_cal["date"].dt.strftime("%m/%d %H:%M")
    df_cal["幣種"] = df_cal["country"].map(country_translate).fillna(df_cal["country"])
    df_cal = df_cal.rename(columns={"title": "事件", "impact": "影響程度", "forecast": "預測值", "previous": "前值"})
    df_cal = df_cal[df_cal["影響程度"].isin(["High", "Medium"])]
    df_cal = df_cal.sort_values("date").reset_index(drop=True)
    df_cal.index += 1
    df_cal["影響程度"] = df_cal["影響程度"].map({"High": "🔴 高", "Medium": "🟡 中"})
    return df_cal[["時間", "幣種", "事件", "影響程度", "預測值", "前值"]]


# ── 資金水位（FRED）─────────────────────────────────────────────────────────

TTL_FRED = 60 * 60 * 6  # 6 小時，FRED 資料每日更新


@st.cache_data(ttl=TTL_FRED)
def get_yield_history() -> pd.DataFrame:
    """2Y / 10Y 美國公債殖利率近3個月，回傳 date/Y2/Y10/spread 欄位。"""
    df2  = _fred("DGS2",  limit=90).rename(columns={"value": "2Y"})
    df10 = _fred("DGS10", limit=90).rename(columns={"value": "10Y"})
    if df2.empty or df10.empty:
        return pd.DataFrame()
    df = pd.merge(df2, df10, on="date", how="inner")
    df["spread"] = (df["10Y"] - df["2Y"]).round(3)  # 正 = 正常；負 = 倒掛
    return df.sort_values("date")


@st.cache_data(ttl=TTL_FRED)
def get_liquidity_history() -> pd.DataFrame:
    """聯準會資金水位三件組（近90天）：銀行準備金、ON RRP、TGA，單位億美元。"""
    series = {
        "準備金": "WRBWFRBL",   # 銀行準備金餘額（週資料）
        "ON_RRP": "RRPONTSYD",  # 隔夜逆回購（日資料）
        "TGA":    "WTREGEN",    # 財政部帳戶（週資料）
    }
    frames = {}
    for label, sid in series.items():
        df = _fred(sid, limit=100)
        if not df.empty:
            frames[label] = df.rename(columns={"value": label}).set_index("date")
    if not frames:
        return pd.DataFrame()
    df_all = pd.concat(frames.values(), axis=1).reset_index()
    df_all = df_all.sort_values("date").dropna(how="all", subset=list(frames.keys()))
    # 換算成兆美元（原始單位：百萬）
    for col in frames.keys():
        if col in df_all.columns:
            df_all[col] = (df_all[col] / 1_000_000).round(3)
    return df_all
