# services/sentiment.py — 籌碼面資料抓取（期交所、TWSE 融資）

import io
import datetime
import pandas as pd
import streamlit as st

from utils.http import safe_request
from config import MARKET_HEADERS, TTL_DAILY


def _recent_trading_dates(n_days=30):
    today = datetime.date.today()
    dates = []
    d = today
    while len(dates) < n_days:
        if d.weekday() < 5:
            dates.append(d)
        d -= datetime.timedelta(days=1)
    return list(reversed(dates))


@st.cache_data(ttl=TTL_DAILY)
def fetch_futures_institutional(date_str, commodity_id):
    url = "https://www.taifex.com.tw/cht/3/futContractsDate"
    payload = {
        "queryType": "1", "goDay": "", "doQuery": "1", "dateaddcnt": "",
        "queryDate": date_str, "commodityId": commodity_id,
    }
    try:
        res = safe_request(url, method="post", headers=MARKET_HEADERS, data=payload)
        if res is None:
            return None
        res.encoding = "utf-8"
        tables = pd.read_html(io.StringIO(res.text))
        if not tables:
            return None
        t = tables[0]
        if len(t) < 7:
            return None
        idcol = t.iloc[:, 2].astype(str)
        oi_net = pd.to_numeric(t.iloc[:, 13], errors="coerce")

        def get_net(identity):
            vals = oi_net[idcol == identity]
            return float(vals.iloc[0]) if len(vals) > 0 else 0.0

        dealer  = get_net("自營商")
        ita     = get_net("投信")
        foreign = get_net("外資")
        total   = float(oi_net.iloc[-1])
        institutional_sum = dealer + ita + foreign
        return {
            "日期": date_str, "自營商淨OI": dealer, "投信淨OI": ita, "外資淨OI": foreign,
            "三大法人合計淨OI": institutional_sum, "全市場合計淨OI": total,
            "散戶推算淨OI": total - institutional_sum,
        }
    except Exception:
        return None


@st.cache_data(ttl=TTL_DAILY)
def fetch_institutional_trend(commodity_id, n_days=20):
    rows = []
    for d in _recent_trading_dates(n_days):
        data = fetch_futures_institutional(d.strftime("%Y/%m/%d"), commodity_id)
        if data:
            rows.append(data)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["日期"] = pd.to_datetime(df["日期"], format="%Y/%m/%d")
    return df.sort_values("日期").reset_index(drop=True)


@st.cache_data(ttl=TTL_DAILY)
def fetch_pc_ratio():
    url = "https://www.taifex.com.tw/cht/3/pcRatio"
    try:
        res = safe_request(url, headers=MARKET_HEADERS)
        if res is None:
            return pd.DataFrame()
        res.encoding = "utf-8"
        df = pd.read_html(io.StringIO(res.text))[0]
        df["日期"] = pd.to_datetime(df["日期"], format="%Y/%m/%d")
        return df.sort_values("日期").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=TTL_DAILY)
def fetch_margin_balance(date_str):
    url = f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={date_str}&selectType=ALL&response=json"
    try:
        res = safe_request(url, headers=MARKET_HEADERS)
        if res is None:
            return None
        data = res.json()
        if data.get("stat") != "OK":
            return None
        rows = data.get("tables", [{}])[0].get("data", [])
        target = next((r for r in rows if "合計" in r[0]), rows[0] if rows else None)
        if target is None:
            return None
        return {
            "日期": date_str,
            "今日餘額": pd.to_numeric(str(target[-1]).replace(",", ""), errors="coerce"),
        }
    except Exception:
        return None


@st.cache_data(ttl=TTL_DAILY)
def fetch_margin_trend(n_days=20):
    rows = []
    for d in _recent_trading_dates(n_days):
        data = fetch_margin_balance(d.strftime("%Y%m%d"))
        if data and pd.notna(data["今日餘額"]):
            rows.append({"日期": d, "融資餘額": data["今日餘額"]})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["日期"] = pd.to_datetime(df["日期"])
    return df.sort_values("日期").reset_index(drop=True)
