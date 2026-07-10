# services/macro.py — 總經資料抓取（Fed 利率、日銀、匯率、行事曆）

import datetime
import pandas as pd
import streamlit as st

from utils.http import yf_chart, safe_request
from config import TTL_INTRADAY, TTL_CALENDAR


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
