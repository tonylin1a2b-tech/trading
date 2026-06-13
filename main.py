import streamlit as st
import requests
import urllib3
import pandas as pd
import datetime
import os
import io
import json
import plotly.graph_objects as go
import xml.etree.ElementTree as ET
from urllib.parse import quote
from streamlit_autorefresh import st_autorefresh
from streamlit_lightweight_charts import renderLightweightCharts
from FinMind.data import DataLoader

urllib3.disable_warnings()

st.set_page_config(page_title="台股交易系統", page_icon="📈", layout="wide")

# ==================== 全域樣式（海洋風）====================
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(180deg, #eaf7fc 0%, #d6eef8 35%, #c2e6f2 100%);
    }
    .block-container { padding-top: 2rem; padding-bottom: 6rem; position: relative; z-index: 1; }
    h1, h2, h3 { font-weight: 700; color: #0b3d5c; }
    h1 {
        padding-bottom: 0.4rem;
        border-bottom: 4px solid transparent;
        border-image: linear-gradient(90deg, #2ec4f1, #a6e6ff, transparent) 1;
    }
    [data-testid="stMetricValue"] { font-size: 1.9rem; color: #0b3d5c; }
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.6);
        border-radius: 10px;
        padding: 0.6rem 0.9rem;
        border: 1px solid rgba(255, 255, 255, 0.8);
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.55);
        backdrop-filter: blur(4px);
        border: 1px solid rgba(255, 255, 255, 0.7) !important;
    }
    [data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.7);
    }
    .stButton > button {
        border-radius: 8px;
        border: 1px solid #6cc5e8;
        background: linear-gradient(135deg, #7fd4f0, #3a8fb7);
        color: #ffffff;
        font-weight: 600;
        transition: all 0.15s ease-in-out;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #93dcf5, #4ba3cc);
        border-color: #3a8fb7;
        color: #ffffff;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0b3d5c 0%, #146a8c 100%);
    }
    [data-testid="stSidebar"] * { color: #f0fbff !important; }
    .compass-card {
        border-radius: 10px;
        padding: 0.7rem 0.9rem;
        margin-bottom: 0.6rem;
        color: #1f2d3a;
        border: 1px solid rgba(255, 255, 255, 0.7);
    }
    .compass-card .label {
        font-size: 0.82rem;
        opacity: 0.7;
        margin-bottom: 2px;
        color: #1f2d3a;
    }
    .compass-card .value {
        font-size: 1.02rem;
        font-weight: 600;
        color: #1f2d3a;
    }
    .compass-overall {
        border-radius: 12px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
        text-align: center;
        font-size: 1.3rem;
        font-weight: 700;
        color: #1f2d3a;
        border: 1px solid rgba(255, 255, 255, 0.7);
    }

    /* 浪花背景裝飾 */
    .ocean-waves {
        position: fixed;
        left: 0; right: 0; bottom: 0;
        height: 160px;
        z-index: 0;
        pointer-events: none;
        background-repeat: repeat-x;
        background-size: 1440px 160px;
    }
    .ocean-waves.layer1 {
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1440 220' preserveAspectRatio='none'%3E%3Cpath fill='%23ffffff' fill-opacity='0.55' d='M0,140 C180,200 360,80 540,140 C720,200 900,80 1080,140 C1260,200 1440,80 1440,140 L1440,220 L0,220 Z'/%3E%3C/svg%3E");
    }
    .ocean-waves.layer2 {
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1440 220' preserveAspectRatio='none'%3E%3Cpath fill='%2387cfe8' fill-opacity='0.45' d='M0,170 C200,110 400,230 600,170 C800,110 1000,230 1200,170 C1300,140 1400,180 1440,170 L1440,220 L0,220 Z'/%3E%3C/svg%3E");
    }
</style>
<div class="ocean-waves layer2"></div>
<div class="ocean-waves layer1"></div>
""", unsafe_allow_html=True)

# ==================== 共用密碼保護 ====================
def check_password():
    """顯示密碼輸入框，密碼正確才放行進入主程式"""
    if st.session_state.get("password_correct", False):
        return True

    st.title("🔒 台股交易系統")
    st.caption("這是僅限受邀朋友使用的私人系統，請輸入存取密碼")
    pwd = st.text_input("請輸入密碼", type="password")

    if pwd:
        if pwd == st.secrets.get("APP_PASSWORD", ""):
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("❌ 密碼錯誤，請再試一次")

    return False

if not check_password():
    st.stop()

# ==================== 共用資料抓取（風向標 / 散戶指標 共用）====================
MARKET_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
}


def _recent_trading_dates(n_days=30):
    today = datetime.date.today()
    dates = []
    d = today
    while len(dates) < n_days:
        if d.weekday() < 5:
            dates.append(d)
        d -= datetime.timedelta(days=1)
    return list(reversed(dates))


@st.cache_data(ttl=60 * 60 * 4)
def fetch_futures_institutional(date_str, commodity_id):
    url = "https://www.taifex.com.tw/cht/3/futContractsDate"
    payload = {
        "queryType": "1", "goDay": "", "doQuery": "1", "dateaddcnt": "",
        "queryDate": date_str, "commodityId": commodity_id,
    }
    try:
        res = requests.post(url, headers=MARKET_HEADERS, data=payload, verify=False, timeout=15)
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

        dealer = get_net("自營商")
        ita = get_net("投信")
        foreign = get_net("外資")
        total = float(oi_net.iloc[-1])
        institutional_sum = dealer + ita + foreign
        return {
            "日期": date_str, "自營商淨OI": dealer, "投信淨OI": ita, "外資淨OI": foreign,
            "三大法人合計淨OI": institutional_sum, "全市場合計淨OI": total,
            "散戶推算淨OI": total - institutional_sum,
        }
    except Exception:
        return None


@st.cache_data(ttl=60 * 60 * 4)
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


@st.cache_data(ttl=60 * 60 * 4)
def fetch_pc_ratio():
    url = "https://www.taifex.com.tw/cht/3/pcRatio"
    res = requests.get(url, headers=MARKET_HEADERS, verify=False, timeout=15)
    res.encoding = "utf-8"
    df = pd.read_html(io.StringIO(res.text))[0]
    df["日期"] = pd.to_datetime(df["日期"], format="%Y/%m/%d")
    return df.sort_values("日期").reset_index(drop=True)


@st.cache_data(ttl=60 * 60 * 4)
def fetch_margin_balance(date_str):
    url = f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={date_str}&selectType=ALL&response=json"
    try:
        res = requests.get(url, headers=MARKET_HEADERS, verify=False, timeout=15)
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


@st.cache_data(ttl=60 * 60 * 4)
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


@st.cache_data(ttl=60 * 20)
def fetch_fedfunds_futures(range_="5d"):
    """抓取美國30天聯邦基金利率期貨（ZQ=F）近期收盤價，價格隱含利率 = 100 - 收盤價，
    用來反映市場對聯準會升降息預期的變化"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/ZQ=F?interval=1d&range={range_}"
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=15)
    data = res.json()
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    df = pd.DataFrame({
        "date": pd.to_datetime([datetime.datetime.fromtimestamp(t) for t in timestamps]),
        "close": closes,
    })
    return df.dropna().sort_values("date").reset_index(drop=True)


@st.cache_data(ttl=60 * 20)
def fetch_taiex_history(range_="6mo"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?interval=1d&range={range_}"
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=15)
    data = res.json()
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    df = pd.DataFrame({
        "date": pd.to_datetime([datetime.datetime.fromtimestamp(t) for t in timestamps]),
        "close": closes,
    })
    return df.dropna().sort_values("date").reset_index(drop=True)


@st.cache_data(ttl=60 * 20)
def fetch_stock_kline(stock_id, interval="1d", range_="6mo"):
    """透過 Yahoo Finance API 取得個股 K 棒資料（含成交量），上市用 .TW，上櫃用 .TWO"""
    headers = {"User-Agent": "Mozilla/5.0"}
    for suffix in (".TW", ".TWO"):
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{stock_id}{suffix}?interval={interval}&range={range_}"
            res = requests.get(url, headers=headers, verify=False, timeout=15)
            data = res.json()
            result = data["chart"]["result"][0]
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


def compute_support_resistance(df_k):
    """根據結構性山頂/山谷計算支撐/壓力位
    回傳 list of (price, label, type)，type 為 "support" 或 "resistance"
    """
    if len(df_k) < 10:
        return []

    close, high, low = df_k["close"], df_k["high"], df_k["low"]
    current = close.iloc[-1]
    levels = []

    res_candidates = []  # (price, label)
    sup_candidates = []

    # 結構性壓力/支撐：某日最高價須高於前3天與後3天的最高價（山頂）；
    # 某日最低價須低於前3天與後3天的最低價（山谷）
    window = 3
    for i in range(window, len(df_k) - window):
        before_high = high.iloc[i - window:i].max()
        after_high = high.iloc[i + 1:i + window + 1].max()
        before_low = low.iloc[i - window:i].min()
        after_low = low.iloc[i + 1:i + window + 1].min()

        if high.iloc[i] > before_high and high.iloc[i] > after_high and high.iloc[i] > current:
            res_candidates.append((high.iloc[i], "結構性壓力(山頂)"))
        if low.iloc[i] < before_low and low.iloc[i] < after_low and low.iloc[i] < current:
            sup_candidates.append((low.iloc[i], "結構性支撐(山谷)"))

    # 上限：壓力一條、支撐一條，取離現價最近者
    if res_candidates:
        price, label = min(res_candidates, key=lambda x: x[0] - current)
        levels.append((price, label, "resistance"))
    if sup_candidates:
        price, label = min(sup_candidates, key=lambda x: current - x[0])
        levels.append((price, label, "support"))

    return levels


def check_stock_alerts(df_k):
    """檢查最新一根K棒是否觸發提醒：成交量異常放大、觸及支撐/壓力"""
    alerts = []
    if len(df_k) < 6:
        return alerts

    volume = df_k["volume"]
    latest_vol = volume.iloc[-1]
    avg5 = volume.iloc[-6:-1].mean()
    if pd.notna(latest_vol) and avg5 > 0 and latest_vol > 1.5 * avg5:
        alerts.append("🔥 成交量異常放大")

    latest_high = df_k["high"].iloc[-1]
    latest_low = df_k["low"].iloc[-1]
    for level_price, _, ltype in compute_support_resistance(df_k):
        if ltype == "resistance" and latest_high >= level_price:
            alerts.append(f"⚠️ 觸及壓力 {level_price:.2f}")
        if ltype == "support" and latest_low <= level_price:
            alerts.append(f"⚠️ 觸及支撐 {level_price:.2f}")

    return alerts


def render_diff_bar_chart(df, date_col, cols_and_names, title, yaxis_title, color_by_sign=False, barmode=None):
    """畫『較前一日變化量』長條圖。cols_and_names 為 [(原始欄位, 圖例名稱), ...]"""
    diff_data = {name: df[col].diff() for col, name in cols_and_names}
    df_diff = pd.DataFrame(diff_data)
    df_diff["日期"] = df[date_col].values
    df_diff = df_diff.dropna(subset=[cols_and_names[0][1]])
    if df_diff.empty:
        return

    fig = go.Figure()
    for _, name in cols_and_names:
        kwargs = {}
        if color_by_sign:
            kwargs["marker_color"] = ["crimson" if v < 0 else "seagreen" for v in df_diff[name]]
        fig.add_trace(go.Bar(x=df_diff["日期"], y=df_diff[name], name=name, **kwargs))
    fig.add_hline(y=0, line_dash="dot", line_color="gray")

    layout = dict(title=title, xaxis_title="日期", yaxis_title=yaxis_title, hovermode="x unified")
    if barmode:
        layout["barmode"] = barmode
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)


@st.cache_data(ttl=60 * 60 * 4)
def fetch_breadth_signal(top_n=100):
    """成交值前 top_n 檔個股中，5日均線 > 20日均線（多頭排列）的檔數統計"""
    api = DataLoader()
    api.login_by_token(api_token=st.secrets["FINMIND_TOKEN"])

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


def _score_tag(score):
    if score > 0:
        return f"+{score}分"
    return f"{score}分"


def _compute_market_compass():
    scores = {}
    details = {}

    # 1. 加權指數技術面（5日均 vs 20日均）
    try:
        df_taiex = fetch_taiex_history("6mo")
        close = df_taiex["close"].iloc[-1]
        ma5 = df_taiex["close"].iloc[-5:].mean()
        ma20 = df_taiex["close"].iloc[-20:].mean()
        if close > ma20 and ma5 > ma20:
            scores["技術面"] = 1
            details["技術面"] = f"🟢 偏多（{_score_tag(1)}）｜指數 {close:,.0f} 站上20日均線 {ma20:,.0f}，且5日均 > 20日均"
        elif close < ma20 and ma5 < ma20:
            scores["技術面"] = -1
            details["技術面"] = f"🔴 偏空（{_score_tag(-1)}）｜指數 {close:,.0f} 跌破20日均線 {ma20:,.0f}，且5日均 < 20日均"
        else:
            scores["技術面"] = 0
            details["技術面"] = f"🟡 中性（{_score_tag(0)}）｜指數 {close:,.0f}，20日均線 {ma20:,.0f}，多空訊號不一致"
    except Exception as e:
        details["技術面"] = f"⚪ 無法取得加權指數資料（{e}）"

    # 2. 散戶指標：小型臺指期貨（MXF）三大法人合計淨部位（作為散戶情緒反指標）
    try:
        df_inst = fetch_institutional_trend("MXF", n_days=10).dropna(subset=["三大法人合計淨OI"])
        if not df_inst.empty:
            latest_date = df_inst["日期"].iloc[-1].strftime("%Y-%m-%d")
            net = df_inst["三大法人合計淨OI"].iloc[-1]
            if len(df_inst) >= 2:
                prev = df_inst["三大法人合計淨OI"].iloc[-2]
                trend = "增加" if net > prev else ("減少" if net < prev else "持平")
            else:
                trend = "—"
            if net > 0:
                scores["法人籌碼"] = 1
                details["法人籌碼"] = f"🟢 偏多（{_score_tag(1)}）｜小台指三大法人合計淨部位（{latest_date}）{int(net):,} 口（淨多單，較前一日{trend}，散戶情緒可能偏空）"
            elif net < 0:
                scores["法人籌碼"] = -1
                details["法人籌碼"] = f"🔴 偏空（{_score_tag(-1)}）｜小台指三大法人合計淨部位（{latest_date}）{int(net):,} 口（淨空單，較前一日{trend}，散戶情緒可能偏多）"
            else:
                scores["法人籌碼"] = 0
                details["法人籌碼"] = f"🟡 中性（{_score_tag(0)}）｜小台指三大法人合計淨部位（{latest_date}）持平"
        else:
            details["法人籌碼"] = "⚪ 無法取得小台指三大法人資料"
    except Exception as e:
        details["法人籌碼"] = f"⚪ 無法取得小台指三大法人資料（{e}）"

    # 3. 選擇權 Put/Call Ratio
    try:
        df_pc = fetch_pc_ratio()
        if not df_pc.empty:
            ratio = df_pc["買賣權未平倉量比率%"].iloc[-1]
            if ratio >= 115:
                scores["PC Ratio"] = -1
                details["PC Ratio"] = f"🔴 偏空（{_score_tag(-1)}）｜未平倉量 PC Ratio {ratio:.1f}%，賣權部位偏多，避險氣氛濃厚"
            elif ratio <= 85:
                scores["PC Ratio"] = 1
                details["PC Ratio"] = f"🟢 偏多（{_score_tag(1)}）｜未平倉量 PC Ratio {ratio:.1f}%，買權部位偏多，市場看多氣氛濃厚"
            else:
                scores["PC Ratio"] = 0
                details["PC Ratio"] = f"🟡 中性（{_score_tag(0)}）｜未平倉量 PC Ratio {ratio:.1f}%，多空氣氛均衡"
        else:
            details["PC Ratio"] = "⚪ 無法取得 PC Ratio 資料"
    except Exception as e:
        details["PC Ratio"] = f"⚪ 無法取得 PC Ratio 資料（{e}）"

    # 4. 融資餘額趨勢
    try:
        df_margin = fetch_margin_trend(n_days=10)
        if len(df_margin) >= 2:
            latest_date = df_margin["日期"].iloc[-1].strftime("%Y-%m-%d")
            latest_m = df_margin["融資餘額"].iloc[-1]
            prev_m = df_margin["融資餘額"].iloc[-2]
            if latest_m > prev_m:
                scores["融資餘額"] = -1
                details["融資餘額"] = f"🔴 警訊（{_score_tag(-1)}）｜融資餘額（{latest_date}）較前一日增加，散戶槓桿增加，風險偏高"
            else:
                scores["融資餘額"] = 0
                if latest_m < prev_m:
                    details["融資餘額"] = f"🟡 中性（{_score_tag(0)}）｜融資餘額（{latest_date}）較前一日減少，散戶降槓桿"
                else:
                    details["融資餘額"] = f"🟡 中性（{_score_tag(0)}）｜融資餘額（{latest_date}）與前一日持平"
        else:
            details["融資餘額"] = "⚪ 無法取得融資餘額資料"
    except Exception as e:
        details["融資餘額"] = f"⚪ 無法取得融資餘額資料（{e}）"

    # 5. 成交值前100檔個股廣度（5日均 > 20日均 多頭排列檔數）
    try:
        breadth = fetch_breadth_signal(100)
        if breadth["valid"] > 0:
            golden, dead, valid = breadth["golden"], breadth["dead"], breadth["valid"]
            if golden > dead:
                scores["個股廣度"] = 1
                details["個股廣度"] = f"🟢 偏多（{_score_tag(1)}）｜成交值前100檔中，5日均>20日均有 {golden}/{valid} 檔（多頭排列居多）"
            elif golden < dead:
                scores["個股廣度"] = -1
                details["個股廣度"] = f"🔴 偏空（{_score_tag(-1)}）｜成交值前100檔中，5日均>20日均僅 {golden}/{valid} 檔（空頭排列居多）"
            else:
                scores["個股廣度"] = 0
                details["個股廣度"] = f"🟡 中性（{_score_tag(0)}）｜成交值前100檔中，多空排列各 {golden} 檔，五五波"
        else:
            details["個股廣度"] = "⚪ 無法取得個股廣度資料"
    except Exception as e:
        details["個股廣度"] = f"⚪ 無法取得個股廣度資料（{e}）"

    # 6. 加權指數位置（站上/跌破 20日均線）
    try:
        df_taiex = fetch_taiex_history("6mo")
        close = df_taiex["close"].iloc[-1]
        ma20 = df_taiex["close"].iloc[-20:].mean()
        if close > ma20:
            scores["指數位置"] = 1
            details["指數位置"] = f"🟢 偏多（{_score_tag(1)}）｜指數 {close:,.0f} 在20日均線 {ma20:,.0f} 之上"
        elif close < ma20:
            scores["指數位置"] = -1
            details["指數位置"] = f"🔴 偏空（{_score_tag(-1)}）｜指數 {close:,.0f} 在20日均線 {ma20:,.0f} 之下"
        else:
            scores["指數位置"] = 0
            details["指數位置"] = f"🟡 中性（{_score_tag(0)}）｜指數 {close:,.0f} 與20日均線 {ma20:,.0f} 持平"
    except Exception as e:
        details["指數位置"] = f"⚪ 無法取得加權指數資料（{e}）"

    # 7. 加權指數 MACD 柱體 vs 前一交易日
    try:
        df_taiex = fetch_taiex_history("6mo")
        close = df_taiex["close"]
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        hist = macd_line - signal_line
        hist_today = hist.iloc[-1]
        hist_prev = hist.iloc[-2]
        if hist_today > hist_prev:
            scores["MACD動能"] = 1
            details["MACD動能"] = f"🟢 偏多（{_score_tag(1)}）｜MACD柱體 {hist_today:.2f} > 前一交易日 {hist_prev:.2f}，動能增強"
        elif hist_today < hist_prev:
            scores["MACD動能"] = -1
            details["MACD動能"] = f"🔴 偏空（{_score_tag(-1)}）｜MACD柱體 {hist_today:.2f} < 前一交易日 {hist_prev:.2f}，動能減弱"
        else:
            scores["MACD動能"] = 0
            details["MACD動能"] = f"🟡 中性（{_score_tag(0)}）｜MACD柱體與前一交易日持平（{hist_today:.2f}）"
    except Exception as e:
        details["MACD動能"] = f"⚪ 無法取得加權指數資料（{e}）"

    # 8. 美國升降息預期（以30天聯邦基金利率期貨 ZQ=F 隱含利率變化為代理指標）
    try:
        df_ff = fetch_fedfunds_futures("5d")
        implied_rate = 100 - df_ff["close"]
        rate_today = implied_rate.iloc[-1]
        rate_prev = implied_rate.iloc[-2]
        change = rate_today - rate_prev
        if change > 0.005:
            scores["美國利率預期"] = -1
            details["美國利率預期"] = f"🔴 偏空（{_score_tag(-1)}）｜聯邦基金利率期貨隱含利率 {rate_today:.3f}%，較前一日 {rate_prev:.3f}% 上升，升息機率提高，不利股市"
        elif change < -0.005:
            scores["美國利率預期"] = 1
            details["美國利率預期"] = f"🟢 偏多（{_score_tag(1)}）｜聯邦基金利率期貨隱含利率 {rate_today:.3f}%，較前一日 {rate_prev:.3f}% 下降，降息機率提高，利好股市"
        else:
            scores["美國利率預期"] = 0
            details["美國利率預期"] = f"🟡 中性（{_score_tag(0)}）｜聯邦基金利率期貨隱含利率 {rate_today:.3f}%，與前一日 {rate_prev:.3f}% 大致持平"
    except Exception as e:
        details["美國利率預期"] = f"⚪ 無法取得美國利率期貨資料（{e}）"

    return scores, details


def render_market_compass():
    """大盤風向標：綜合大盤技術面、三大法人期貨部位、PC Ratio、融資餘額、個股廣度、指數位置、MACD動能、美國升降息預期，給出多空燈號。每天只計算一次並鎖定快取"""
    st.subheader("📡 大盤風向標")
    st.caption("綜合「加權指數技術面」「散戶指標(小台指三大法人合計淨部位)」「選擇權 Put/Call Ratio」「融資餘額趨勢」「成交值前100檔個股5日均/20日均廣度」「指數20日均線位置」「MACD柱體動能」「美國升降息預期(聯邦基金利率期貨)」八項指標，給出大盤多空參考燈號（非投資建議）。每天僅計算一次，當日重新整理不會重新呼叫 API")

    CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
    os.makedirs(CACHE_DIR, exist_ok=True)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    cache_file = os.path.join(CACHE_DIR, f"compass_{today_str}.json")

    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)
        scores, details = cached["scores"], cached["details"]
    else:
        scores, details = _compute_market_compass()
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"scores": scores, "details": details}, f, ensure_ascii=False)

    total = sum(scores.values())
    if total >= 2:
        overall = "🟢 偏多"
        overall_bg, overall_border = "#d9f2e3", "#2ecc71"
    elif total <= -2:
        overall = "🔴 偏空"
        overall_bg, overall_border = "#fbdede", "#e74c3c"
    else:
        overall = "🟡 中性"
        overall_bg, overall_border = "#fbf3d4", "#f1c40f"

    st.markdown(
        f"""<div class="compass-overall" style="background:{overall_bg};border:1px solid {overall_border};">
            綜合燈號：{overall}　（總分 {total:+d} / {len(scores)} 項指標）
        </div>""",
        unsafe_allow_html=True,
    )

    def _card_colors(text):
        if text.startswith("🟢"):
            return "#d9f2e3", "#2ecc71"
        if text.startswith("🔴"):
            return "#fbdede", "#e74c3c"
        if text.startswith("🟡"):
            return "#fbf3d4", "#f1c40f"
        return "#eef2f5", "#999"

    keys = ["技術面", "法人籌碼", "PC Ratio", "融資餘額", "個股廣度", "指數位置", "MACD動能", "美國利率預期"]
    cols1 = st.columns(4)
    cols2 = st.columns(4)
    for i, key in enumerate(keys):
        col = cols1[i] if i < 4 else cols2[i - 4]
        with col:
            value = details.get(key, "⚪ 無資料")
            bg, border = _card_colors(value)
            st.markdown(
                f"""<div class="compass-card" style="background:{bg};border-left:4px solid {border};">
                    <div class="label">{key}</div>
                    <div class="value">{value}</div>
                </div>""",
                unsafe_allow_html=True,
            )


# 側邊欄選單
st.sidebar.title("📊 台股交易系統")
page = st.sidebar.radio("選擇頁面", ["🏠 選股系統", "🌍 總經儀表板", "📰 新聞監控", "📊 散戶指標", "💼 持股監控"])

# ==================== 選股系統 ====================
if page == "🏠 選股系統":
    st.title("台股動能選股")
    st_autorefresh(interval=20 * 60 * 1000, key="stock_refresh")

    with st.spinner("載入大盤風向標中..."):
        render_market_compass()

    st.divider()

    # ------------------------------
    # 選股條件設定：使用者先設定條件，再按下「開始選股」才執行掃描
    # ------------------------------
    st.subheader("🔧 選股條件設定")
    with st.container(border=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            top_n = st.number_input("成交值排名前 N 檔", min_value=20, max_value=300, value=100, step=10)
        with col2:
            ma_period = st.selectbox("均線天數", [5, 10, 20, 60], index=2)
        with col3:
            range_pct = st.slider("距均線範圍（±%）", min_value=0.5, max_value=10.0, value=3.0, step=0.5)

        EXTRA_OPTIONS = [
            "📈 營收創新高（近12個月）",
            "📊 成交量放大（>1.5倍5日均量）",
            "🔀 5日均線 > 20日均線（短多排列）",
        ]
        extra_filters = st.multiselect("額外篩選條件（可複選）", EXTRA_OPTIONS)
        if "📈 營收創新高（近12個月）" in extra_filters:
            st.caption("⚠️ 「營收創新高」需要對每檔股票額外查詢月營收資料，掃描時間會明顯變長")

        ext_flags = {
            "rev_high": EXTRA_OPTIONS[0] in extra_filters,
            "vol_expand": EXTRA_OPTIONS[1] in extra_filters,
            "golden": EXTRA_OPTIONS[2] in extra_filters,
        }

        run_screen = st.button("🔍 開始選股", type="primary")

    # ------------------------------
    # 每日結果鎖定快取：相同條件當天跑過一次後，結果存成檔案，
    # 同一天內重新整理頁面就直接讀檔，不再呼叫 FinMind API，避免浪費 token 額度
    # ------------------------------
    CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
    os.makedirs(CACHE_DIR, exist_ok=True)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    ext_key = f"r{int(ext_flags['rev_high'])}v{int(ext_flags['vol_expand'])}g{int(ext_flags['golden'])}"
    cache_file = os.path.join(CACHE_DIR, f"screener_{today_str}_top{top_n}_ma{ma_period}_pm{range_pct}_{ext_key}.csv")

    DISPLAY_COLS = list(dict.fromkeys(
        ["證券代號", "證券名稱", "成交金額(億)", "收盤價_x", f"{ma_period}日均線", "距均線(%)",
         "5日均線", "20日均線", "成交量(張)", "5日均量(張)"]
    ))
    if ext_flags["rev_high"]:
        DISPLAY_COLS.append("近12月營收創高")

    TV_LINK_CONFIG = {"證券代號": st.column_config.LinkColumn("證券代號", display_text=r"symbol=TWSE:(\d+)")}

    def with_tradingview_link(df):
        df = df.copy()
        df["證券代號"] = "https://www.tradingview.com/chart/?symbol=TWSE:" + df["證券代號"].astype(str)
        return df

    if os.path.exists(cache_file):
        st.success(f"📌 今天（{today_str}）已經用相同條件跑過選股，直接讀取鎖定的結果，不重新呼叫 API")
        result = pd.read_csv(cache_file)
        result.index = range(1, len(result) + 1)
        st.subheader(f"資料日期：{today_str}　符合條件：{len(result)} 檔")
        st.dataframe(with_tradingview_link(result[[c for c in DISPLAY_COLS if c in result.columns]]), column_config=TV_LINK_CONFIG, use_container_width=True)
    elif run_screen:
        api = DataLoader()
        api.login_by_token(api_token=st.secrets["FINMIND_TOKEN"])

        with st.spinner(f"正在抓取成交值前{top_n}名..."):
            stock_info = api.taiwan_stock_info()
            stock_info = stock_info[~stock_info["industry_category"].str.contains("ETF|基金", na=False)]
            stock_info = stock_info[stock_info["stock_id"].str.match(r"^\d{4}$")]
            valid_stocks = set(stock_info["stock_id"].tolist())

            url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json"
            res = requests.get(url)
            data = res.json()
            df = pd.DataFrame(data["data"], columns=data["fields"])
            df = df[df["證券代號"].isin(valid_stocks)]
            df["成交金額"] = df["成交金額"].str.replace(",", "").astype(float)
            df["成交金額(億)"] = (df["成交金額"] / 1e8).round(2)
            topN = df.sort_values("成交金額", ascending=False).head(top_n).reset_index(drop=True)
            stock_ids = topN["證券代號"].tolist()

        with st.spinner(f"套用篩選條件中，請稍候..."):
            end_date = datetime.date.today().strftime("%Y-%m-%d")
            lookback_days = max(ma_period, 20) * 3 + 30
            start_date = (datetime.date.today() - datetime.timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            rev_start_date = (datetime.date.today() - datetime.timedelta(days=400)).strftime("%Y-%m-%d")

            result_list = []
            for sid in stock_ids:
                try:
                    price = api.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=end_date)
                    if len(price) < max(ma_period, 20, 6):
                        continue
                    price = price.sort_values("date")

                    ma = price["close"].iloc[-ma_period:].mean()
                    close = price["close"].iloc[-1]
                    diff_pct = (close - ma) / ma * 100
                    if not (-range_pct <= diff_pct <= range_pct):
                        continue

                    ma5 = price["close"].iloc[-5:].mean()
                    ma20 = price["close"].iloc[-20:].mean()
                    if ext_flags["golden"] and not (ma5 > ma20):
                        continue

                    vol_ma5 = price["Trading_Volume"].iloc[-6:-1].mean()
                    latest_vol = price["Trading_Volume"].iloc[-1]
                    vol_expand = vol_ma5 > 0 and latest_vol > 1.5 * vol_ma5
                    if ext_flags["vol_expand"] and not vol_expand:
                        continue

                    row = {
                        "證券代號": sid,
                        f"{ma_period}日均線": round(ma, 2),
                        "收盤價": close,
                        "距均線(%)": round(diff_pct, 2),
                        "5日均線": round(ma5, 2),
                        "20日均線": round(ma20, 2),
                        "成交量(張)": int(latest_vol / 1000),
                        "5日均量(張)": int(vol_ma5 / 1000),
                    }

                    if ext_flags["rev_high"]:
                        rev = api.taiwan_stock_month_revenue(stock_id=sid, start_date=rev_start_date, end_date=end_date)
                        if len(rev) < 2:
                            continue
                        rev = rev.sort_values("date")
                        is_rev_high = rev["revenue"].iloc[-1] >= rev["revenue"].max()
                        if not is_rev_high:
                            continue
                        row["近12月營收創高"] = "✅"

                    result_list.append(row)
                except:
                    pass

            if result_list:
                result = topN.merge(pd.DataFrame(result_list), on="證券代號", how="inner")
                result = result.sort_values("距均線(%)", key=abs).reset_index(drop=True)
            else:
                result = pd.DataFrame(columns=DISPLAY_COLS)

        # 鎖定結果：存成當天的快取檔（依條件區分），之後重新整理就不用再打 API
        result.to_csv(cache_file, index=False, encoding="utf-8-sig")
        st.success(f"✅ 選股結果已鎖定並存檔，今天內用相同條件重新整理將直接讀取，不再消耗 API 額度")

        result.index = range(1, len(result) + 1)
        st.subheader(f"資料日期：{today_str}　符合條件：{len(result)} 檔")
        st.dataframe(with_tradingview_link(result[[c for c in DISPLAY_COLS if c in result.columns]]), column_config=TV_LINK_CONFIG, use_container_width=True)
    else:
        st.info("👆 請設定好選股條件後，點擊「開始選股」按鈕進行掃描")

# ==================== 總經儀表板 ====================
elif page == "🌍 總經儀表板":
    st.title("總經儀表板")
    st_autorefresh(interval=20 * 60 * 1000, key="macro_refresh")

    @st.cache_data(ttl=60 * 20)
    def get_fed_probability():
        current_rate = 4.25
        meetings = {
            "2026-07-30": "ZQN26.CBT",
            "2026-09-17": "ZQU26.CBT",
            "2026-11-05": "ZQX26.CBT",
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        result = []
        for date, symbol in meetings.items():
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
            res = requests.get(url, headers=headers, verify=False)
            data = res.json()
            price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
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
                "方向": direction
            })
        return result

    @st.cache_data(ttl=60 * 20)
    def get_history(symbol, label):
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=3mo"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, verify=False)
        data = res.json()
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        df = pd.DataFrame({
            "date": pd.to_datetime([datetime.datetime.fromtimestamp(t) for t in timestamps]),
            label: [round(100 - c, 4) if c else None for c in closes]
        })
        return df.dropna().sort_values("date")

    @st.cache_data(ttl=60 * 20)
    def get_boj_history():
        url = "https://query1.finance.yahoo.com/v8/finance/chart/2621.T?interval=1d&range=3mo"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, verify=False)
        data = res.json()
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        df = pd.DataFrame({
            "date": pd.to_datetime([datetime.datetime.fromtimestamp(t) for t in timestamps]),
            "JGB_ETF": closes
        })
        df = df[df["JGB_ETF"].notna()]
        df = df[df["JGB_ETF"] > 0]
        return df.sort_values("date")

    st.subheader("🇺🇸 Fed 升降息預期")
    with st.spinner("載入中..."):
        fed_data = get_fed_probability()
        st.dataframe(fed_data, use_container_width=True)

    st.subheader("📈 Fed 隱含利率趨勢（近3個月）")
    with st.spinner("載入趨勢圖..."):
        df_jul = get_history("ZQN26.CBT", "7月會議")
        df_sep = get_history("ZQU26.CBT", "9月會議")
        df_nov = get_history("ZQX26.CBT", "11月會議")

        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=df_jul["date"], y=df_jul["7月會議"], name="7月會議"))
        fig1.add_trace(go.Scatter(x=df_sep["date"], y=df_sep["9月會議"], name="9月會議"))
        fig1.add_trace(go.Scatter(x=df_nov["date"], y=df_nov["11月會議"], name="11月會議"))
        fig1.update_layout(title="Fed 隱含利率趨勢", xaxis_title="日期", yaxis_title="隱含利率 (%)", hovermode="x unified")
        st.plotly_chart(fig1, use_container_width=True)

    st.subheader("🇯🇵 日銀政策方向（日本公債ETF趨勢）")
    st.caption("ETF價格上漲 = 殖利率下降 = 市場預期不升息｜ETF價格下跌 = 市場預期升息")
    st.info("🗓️ 下次日銀會議：2026年6月16日〜17日")

    with st.spinner("載入日銀趨勢圖..."):
        df_boj = get_boj_history()
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df_boj["date"], y=df_boj["JGB_ETF"], name="日本公債ETF"))
        fig2.update_layout(title="日本公債ETF價格趨勢", xaxis_title="日期", yaxis_title="ETF 價格 (JPY)", hovermode="x unified")
        st.plotly_chart(fig2, use_container_width=True)

    @st.cache_data(ttl=60 * 20)
    def get_calendar():
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(url, headers=headers, verify=False, timeout=10)
        events = res.json()
        country_translate = {"USD": "🇺🇸 美元", "JPY": "🇯🇵 日圓", "EUR": "🇪🇺 歐元", "GBP": "🇬🇧 英鎊", "AUD": "🇦🇺 澳幣", "CAD": "🇨🇦 加幣", "NZD": "🇳🇿 紐幣", "CHF": "🇨🇭 瑞郎"}
        df_cal = pd.DataFrame(events)
        df_cal["date"] = pd.to_datetime(df_cal["date"]).dt.tz_convert("Asia/Taipei")
        df_cal["時間"] = df_cal["date"].dt.strftime("%m/%d %H:%M")
        df_cal["幣種"] = df_cal["country"].map(country_translate).fillna(df_cal["country"])
        df_cal = df_cal.rename(columns={"title": "事件", "impact": "影響程度", "forecast": "預測值", "previous": "前值"})
        df_cal = df_cal[df_cal["影響程度"].isin(["High", "Medium"])]
        df_cal = df_cal.sort_values("date").reset_index(drop=True)
        df_cal.index += 1
        df_cal["影響程度"] = df_cal["影響程度"].map({"High": "🔴 高", "Medium": "🟡 中"})
        return df_cal[["時間", "幣種", "事件", "影響程度", "預測值", "前值"]]

    st.subheader("📅 本週總經行事曆")
    with st.spinner("載入行事曆..."):
        try:
            st.dataframe(get_calendar(), use_container_width=True)
        except Exception as e:
            st.warning(f"行事曆暫時無法載入，請稍後再試。({e})")

# ==================== 新聞監控 ====================
elif page == "📰 新聞監控":
    st.title("📰 新聞關鍵字監控")
    st_autorefresh(interval=60 * 60 * 1000, key="news_refresh")

    # 監控關鍵字（顯示名稱 → 中英文搜尋詞組合）
    NEWS_KEYWORDS = {
        "流動性": ["流動性", "liquidity"],
        "IPO": ["IPO", "首次公開發行"],
        "總經": ["總經", "總體經濟", "macro economy"],
        "戰爭": ["戰爭", "war", "衝突"],
    }

    BULLISH_WORDS = [
        "降息", "寬鬆", "上修", "成長", "增加", "回升", "樂觀", "激勵", "利多",
        "看好", "提升", "擴大", "復甦", "緩解", "降溫", "觸底", "反彈", "創新高",
        "熱絡", "暢旺", "獲利", "爆發", "強勁", "回穩", "止穩", "轉強",
    ]
    BEARISH_WORDS = [
        "升息", "緊縮", "下修", "衰退", "下滑", "萎縮", "悲觀", "利空", "看壞",
        "風險", "暴跌", "崩盤", "戰爭", "制裁", "衝突", "短缺", "枯竭", "收緊",
        "壓力", "殺手", "擔憂", "閃崩", "重挫", "走弱", "惡化", "通膨", "違約",
        "裁員", "倒閉", "下跌", "拋售", "恐慌",
    ]

    def classify_sentiment(title: str) -> str:
        bull_score = sum(1 for w in BULLISH_WORDS if w in title)
        bear_score = sum(1 for w in BEARISH_WORDS if w in title)
        if bull_score > bear_score:
            return "🟢 利多"
        elif bear_score > bull_score:
            return "🔴 利空"
        else:
            return "⚪ 中性"

    def _is_english(text):
        try:
            text.encode("ascii")
            return True
        except UnicodeEncodeError:
            return False

    def _fetch_one_news(query, limit):
        # 英文搜尋詞改用美國/英文語系查詢，才能搜到 Reuters/Bloomberg/Yahoo Finance/CNBC 等主流英文媒體
        if _is_english(query):
            locale_params = "hl=en-US&gl=US&ceid=US:en"
        else:
            locale_params = "hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        url = f"https://news.google.com/rss/search?q={quote(query + ' when:1d')}&{locale_params}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(url, headers=headers, verify=False, timeout=10)
        root = ET.fromstring(res.content)
        items = root.findall(".//item")[:limit]
        rows = []
        for it in items:
            title = it.findtext("title", "")
            link = it.findtext("link", "")
            pub_date = it.findtext("pubDate", "")
            source = it.find("source")
            source_name = source.text if source is not None else ""
            try:
                dt = pd.to_datetime(pub_date, utc=True).tz_convert("Asia/Taipei")
                time_str = dt.strftime("%m/%d %H:%M")
                sort_key = dt
            except Exception:
                time_str = pub_date
                sort_key = pd.Timestamp("1970-01-01", tz="Asia/Taipei")
            rows.append({
                "時間": time_str, "標題": title, "來源": source_name,
                "情緒": classify_sentiment(title), "連結": link, "_sort": sort_key,
            })
        return rows

    @st.cache_data(ttl=60 * 60)
    def fetch_news(queries, fetch_limit=40, display_limit=25):
        all_rows = []
        for q in queries:
            all_rows.extend(_fetch_one_news(q, fetch_limit))
        if not all_rows:
            return pd.DataFrame(columns=["時間", "標題", "來源", "情緒", "連結"])
        df = pd.DataFrame(all_rows)
        df = df.drop_duplicates(subset=["標題"])
        cutoff = pd.Timestamp.now(tz="Asia/Taipei") - pd.Timedelta(hours=24)
        df = df[df["_sort"] >= cutoff]
        df = df.sort_values("_sort", ascending=False).head(display_limit)
        return df.drop(columns=["_sort"]).reset_index(drop=True)

    st.caption("資料來源：Google News RSS（每小時自動更新一次，僅顯示近 24 小時內新聞）｜ 情緒分類為「規則式關鍵字比對」，僅供參考，非專業投資建議")

    # ------------------------------
    # 📋 匯出台美股相關新聞給 AI 判讀（手動複製貼上版本，不需要 API key）
    # ------------------------------
    st.subheader("📋 匯出台美股相關新聞給 AI 判讀")
    st.caption("不需要 API key：篩選出跟台美股相關的新聞後，整理成文字，複製貼到與 Claude 的對話視窗，即可請 AI 幫你分析摘要、標註利多利空")

    TW_US_STOCK_KEYWORDS = [
        "台股", "台積電", "台灣50", "0050", "上市", "上櫃", "櫃買", "證交所", "台指期",
        "美股", "那斯達克", "NASDAQ", "道瓊", "S&P", "標普", "費半", "美國股市",
        "輝達", "NVIDIA", "蘋果", "Apple", "特斯拉", "Tesla", "微軟", "Microsoft",
        "聯準會", "Fed", "FOMC", "升息", "降息", "殖利率", "美元", "台幣",
        "那斯達克100", "美國經濟", "美債", "那指", "費城半導體",
    ]

    def filter_relevant_for_summary(df_all):
        if df_all is None or len(df_all) == 0:
            return df_all
        mask = df_all["標題"].apply(lambda t: any(kw in t for kw in TW_US_STOCK_KEYWORDS))
        return df_all[mask].reset_index(drop=True)

    with st.spinner("正在篩選台美股相關新聞..."):
        try:
            all_news_frames = []
            for label, queries in NEWS_KEYWORDS.items():
                df_kw = fetch_news(queries, fetch_limit=40, display_limit=25)
                if len(df_kw) > 0:
                    all_news_frames.append(df_kw)

            if all_news_frames:
                df_all_news = pd.concat(all_news_frames, ignore_index=True).drop_duplicates(subset=["標題"])
                df_relevant = filter_relevant_for_summary(df_all_news)
            else:
                df_relevant = pd.DataFrame(columns=["標題"])

            st.caption(f"篩選出 {len(df_relevant)} 則與台美股相關的新聞")

            if len(df_relevant) == 0:
                st.info("目前抓到的新聞中，沒有明顯跟台美股相關的內容可供匯出。")
            else:
                export_lines = [
                    "請幫我分析以下近期台股/美股相關新聞標題，整理出3~6條重點摘要（條列式），",
                    "並標註每條偏向「利多」、「利空」或「中性偏觀察」，最後給一句整體市場情緒總結：",
                    "",
                ]
                for _, row in df_relevant.iterrows():
                    export_lines.append(f"- [{row['時間']}] {row['標題']}（來源：{row['來源']}）")
                export_text = "\n".join(export_lines)

                st.text_area(
                    "👇 點選文字框內容（Ctrl+A 全選、Ctrl+C 複製），貼到與 Claude 的對話視窗即可請它幫你判讀分析",
                    value=export_text,
                    height=320,
                )

                with st.expander("📰 查看篩選出的新聞清單（含連結）"):
                    for _, row in df_relevant.iterrows():
                        st.markdown(f"- {row['情緒']} | {row['時間']} | [{row['標題']}]({row['連結']})")

        except Exception as e:
            st.warning(f"新聞篩選失敗，請稍後再試。({e})")

    st.divider()

    news_tabs = st.tabs([f"🔍 {label}" for label in NEWS_KEYWORDS])
    for tab, (label, queries) in zip(news_tabs, NEWS_KEYWORDS.items()):
        with tab:
            st.caption(f"搜尋詞：{'、'.join(queries)}")
            with st.spinner(f"載入「{label}」相關新聞（中英文搜尋）..."):
                try:
                    df_news = fetch_news(queries, fetch_limit=40, display_limit=25)
                    if len(df_news) == 0:
                        st.info("目前查無相關新聞")
                    else:
                        bull_count = (df_news["情緒"] == "🟢 利多").sum()
                        bear_count = (df_news["情緒"] == "🔴 利空").sum()
                        neutral_count = (df_news["情緒"] == "⚪ 中性").sum()
                        col1, col2, col3 = st.columns(3)
                        col1.metric("🟢 利多新聞", f"{bull_count} 則")
                        col2.metric("🔴 利空新聞", f"{bear_count} 則")
                        col3.metric("⚪ 中性新聞", f"{neutral_count} 則")
                        for _, row in df_news.iterrows():
                            st.markdown(
                                f"**{row['情緒']}** | {row['時間']} | {row['來源']}  \n"
                                f"[{row['標題']}]({row['連結']})"
                            )
                            st.divider()
                except Exception as e:
                    st.warning(f"新聞載入失敗，請稍後再試。({e})")

# ==================== 散戶指標 ====================
elif page == "📊 散戶指標":
    st.title("📊 大盤散戶指標")
    st.caption("資料來源：台灣期貨交易所（TAIFEX）、證交所（TWSE）｜ 散戶部位為「推算值」（總未平倉 − 三大法人合計），僅供參考，非專業投資建議")

    st_autorefresh(interval=30 * 60 * 1000, key="retail_refresh")

    RETAIL_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    def _recent_trading_dates(n_days=30):
        today = datetime.date.today()
        dates = []
        d = today
        while len(dates) < n_days:
            if d.weekday() < 5:
                dates.append(d)
            d -= datetime.timedelta(days=1)
        return list(reversed(dates))

    @st.cache_data(ttl=60 * 60 * 4)
    def _fetch_futures_institutional(date_str, commodity_id):
        url = "https://www.taifex.com.tw/cht/3/futContractsDate"
        payload = {
            "queryType": "1", "goDay": "", "doQuery": "1", "dateaddcnt": "",
            "queryDate": date_str, "commodityId": commodity_id,
        }
        try:
            res = requests.post(url, headers=RETAIL_HEADERS, data=payload, verify=False, timeout=15)
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

            dealer = get_net("自營商")
            ita = get_net("投信")
            foreign = get_net("外資")
            total = float(oi_net.iloc[-1])
            institutional_sum = dealer + ita + foreign
            return {
                "日期": date_str, "自營商淨OI": dealer, "投信淨OI": ita, "外資淨OI": foreign,
                "三大法人合計淨OI": institutional_sum, "全市場合計淨OI": total,
                "散戶推算淨OI": total - institutional_sum,
            }
        except Exception:
            return None

    @st.cache_data(ttl=60 * 60 * 4)
    def _fetch_institutional_trend(commodity_id, n_days=20):
        rows = []
        for d in _recent_trading_dates(n_days):
            data = _fetch_futures_institutional(d.strftime("%Y/%m/%d"), commodity_id)
            if data:
                rows.append(data)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["日期"] = pd.to_datetime(df["日期"], format="%Y/%m/%d")
        return df.sort_values("日期").reset_index(drop=True)

    @st.cache_data(ttl=60 * 60 * 4)
    def _fetch_pc_ratio():
        url = "https://www.taifex.com.tw/cht/3/pcRatio"
        res = requests.get(url, headers=RETAIL_HEADERS, verify=False, timeout=15)
        res.encoding = "utf-8"
        df = pd.read_html(io.StringIO(res.text))[0]
        df["日期"] = pd.to_datetime(df["日期"], format="%Y/%m/%d")
        return df.sort_values("日期").reset_index(drop=True)

    @st.cache_data(ttl=60 * 60 * 4)
    def _fetch_margin_balance(date_str):
        url = f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={date_str}&selectType=ALL&response=json"
        try:
            res = requests.get(url, headers=RETAIL_HEADERS, verify=False, timeout=15)
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

    @st.cache_data(ttl=60 * 60 * 4)
    def _fetch_margin_trend(n_days=20):
        rows = []
        for d in _recent_trading_dates(n_days):
            data = _fetch_margin_balance(d.strftime("%Y%m%d"))
            if data and pd.notna(data["今日餘額"]):
                rows.append({"日期": d, "融資餘額": data["今日餘額"]})
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["日期"] = pd.to_datetime(df["日期"])
        return df.sort_values("日期").reset_index(drop=True)

    # 1. 三大法人合計淨部位（小台 + 微台，作為法人籌碼/散戶情緒反向參考指標）
    st.caption("⚠️ 說明：TAIFEX 公布的「三大法人」報表中，「期貨合計」欄位本身就是「自營商+投信+外資」三者的加總（並非全市場含散戶的未平倉量），因此無法用「全市場 − 三大法人」推算散戶部位（這樣算出來恆為 0）。"
               "改以「三大法人合計淨部位」本身作為法人籌碼動向的代理指標：當法人由空翻多（或淨多單持續增加）時，市場氣氛通常偏多；反之則偏空，可作為散戶情緒的反向參考。")

    def _render_institutional_section(commodity_id, label, color):
        st.subheader(f"🏦 三大法人合計淨部位（{label}）")
        with st.spinner(f"載入{label}三大法人淨部位趨勢中（首次載入需逐日查詢，請稍候）..."):
            df_r = _fetch_institutional_trend(commodity_id, n_days=20)
            df_r = df_r.dropna(subset=["三大法人合計淨OI"])
            if df_r.empty:
                st.warning(f"目前無法取得{label}三大法人資料，請稍後再試。")
                return

            latest_r = df_r.iloc[-1]
            latest_date = latest_r["日期"].strftime("%Y-%m-%d")
            net = latest_r["三大法人合計淨OI"]
            direction = "偏多（淨多單）" if net > 0 else ("偏空（淨空單）" if net < 0 else "持平")

            if len(df_r) >= 2:
                prev_r = df_r.iloc[-2]
                delta_val = net - prev_r["三大法人合計淨OI"]
                st.metric(f"{label} 三大法人合計淨部位（{direction}）｜資料日期：{latest_date}", f"{int(net):,} 口",
                          delta=f"{int(delta_val):,}（較前一日）")
            else:
                st.metric(f"{label} 三大法人合計淨部位（{direction}）｜資料日期：{latest_date}", f"{int(net):,} 口")

            fig_r = go.Figure()
            fig_r.add_trace(go.Scatter(x=df_r["日期"], y=df_r["三大法人合計淨OI"], name="三大法人合計淨部位", line=dict(color=color)))
            fig_r.add_hline(y=0, line_dash="dot", line_color="gray")
            fig_r.update_layout(title=f"三大法人合計淨部位趨勢 - {label}（近20個交易日，正值=偏多／負值=偏空）",
                                xaxis_title="日期", yaxis_title="淨部位（口）", hovermode="x unified")
            st.plotly_chart(fig_r, use_container_width=True)

            render_diff_bar_chart(
                df_r, "日期", [("三大法人合計淨OI", "三大法人淨部位較前一日變化")],
                f"三大法人合計淨部位「較前一日」變化量 - {label}", "變化量（口）", color_by_sign=True,
            )

    _render_institutional_section("MXF", "小型臺指期貨", "darkorange")
    st.markdown("")
    _render_institutional_section("TMF", "微型臺指期貨", "mediumpurple")

    st.divider()

    # 2. Put/Call Ratio
    st.subheader("📈 選擇權 Put/Call Ratio（籌碼面氣氛指標）")
    st.caption("比率越高代表賣權（put）相對買權（call）的量能/未平倉越大，市場避險或看空情緒較濃；比率越低則反映看多氣氛較濃")
    with st.spinner("載入 Put/Call Ratio 中..."):
        try:
            df_pc = _fetch_pc_ratio()
            if df_pc.empty:
                st.info("目前查無 Put/Call Ratio 資料")
            else:
                latest_pc = df_pc.iloc[-1]
                col1, col2 = st.columns(2)
                if len(df_pc) >= 2:
                    prev_pc = df_pc.iloc[-2]
                    col1.metric("買賣權成交量比率 (%)", f"{latest_pc['買賣權成交量比率%']:.2f}",
                                delta=f"{latest_pc['買賣權成交量比率%'] - prev_pc['買賣權成交量比率%']:.2f}（較前一日）")
                    col2.metric("買賣權未平倉量比率 (%)", f"{latest_pc['買賣權未平倉量比率%']:.2f}",
                                delta=f"{latest_pc['買賣權未平倉量比率%'] - prev_pc['買賣權未平倉量比率%']:.2f}（較前一日）")
                else:
                    col1.metric("買賣權成交量比率 (%)", f"{latest_pc['買賣權成交量比率%']:.2f}")
                    col2.metric("買賣權未平倉量比率 (%)", f"{latest_pc['買賣權未平倉量比率%']:.2f}")

                fig_pc = go.Figure()
                fig_pc.add_trace(go.Scatter(x=df_pc["日期"], y=df_pc["買賣權成交量比率%"], name="成交量 Put/Call Ratio"))
                fig_pc.add_trace(go.Scatter(x=df_pc["日期"], y=df_pc["買賣權未平倉量比率%"], name="未平倉量 Put/Call Ratio"))
                fig_pc.add_hline(y=100, line_dash="dot", line_color="gray")
                fig_pc.update_layout(title="Put/Call Ratio 趨勢", xaxis_title="日期", yaxis_title="比率 (%)", hovermode="x unified")
                st.plotly_chart(fig_pc, use_container_width=True)

                # 與前一日差距
                render_diff_bar_chart(
                    df_pc, "日期",
                    [("買賣權成交量比率%", "成交量比率較前一日變化"), ("買賣權未平倉量比率%", "未平倉量比率較前一日變化")],
                    "Put/Call Ratio「較前一日」變化量", "變化量（百分點）", barmode="group",
                )
        except Exception as e:
            st.warning(f"Put/Call Ratio 載入失敗，請稍後再試。({e})")

    st.divider()

    # 3. 三大法人台指期貨淨部位趨勢（大台）
    st.subheader("🏦 三大法人台指期貨淨部位趨勢（大台指）")
    st.caption("自營商／投信／外資在「臺股期貨」未平倉淨部位的多空變化，反映法人對大盤中長期方向的籌碼佈局")
    with st.spinner("載入三大法人淨部位趨勢中..."):
        df_inst = _fetch_institutional_trend("TXF", n_days=20)
        if df_inst.empty:
            st.warning("目前無法取得三大法人資料，請稍後再試。")
        else:
            fig_inst = go.Figure()
            fig_inst.add_trace(go.Scatter(x=df_inst["日期"], y=df_inst["自營商淨OI"], name="自營商"))
            fig_inst.add_trace(go.Scatter(x=df_inst["日期"], y=df_inst["投信淨OI"], name="投信"))
            fig_inst.add_trace(go.Scatter(x=df_inst["日期"], y=df_inst["外資淨OI"], name="外資"))
            fig_inst.add_hline(y=0, line_dash="dot", line_color="gray")
            fig_inst.update_layout(title="三大法人臺股期貨淨部位趨勢（近20個交易日）", xaxis_title="日期", yaxis_title="淨部位（口）", hovermode="x unified")
            st.plotly_chart(fig_inst, use_container_width=True)

            latest_inst = df_inst.iloc[-1]
            if len(df_inst) >= 2:
                prev_inst = df_inst.iloc[-2]
                col1, col2, col3 = st.columns(3)
                col1.metric("自營商淨部位（口）", f"{int(latest_inst['自營商淨OI']):,}",
                            delta=f"{int(latest_inst['自營商淨OI'] - prev_inst['自營商淨OI']):,}（較前一日）")
                col2.metric("投信淨部位（口）", f"{int(latest_inst['投信淨OI']):,}",
                            delta=f"{int(latest_inst['投信淨OI'] - prev_inst['投信淨OI']):,}（較前一日）")
                col3.metric("外資淨部位（口）", f"{int(latest_inst['外資淨OI']):,}",
                            delta=f"{int(latest_inst['外資淨OI'] - prev_inst['外資淨OI']):,}（較前一日）")

            render_diff_bar_chart(
                df_inst, "日期",
                [("自營商淨OI", "自營商較前一日變化"), ("投信淨OI", "投信較前一日變化"), ("外資淨OI", "外資較前一日變化")],
                "三大法人淨部位「較前一日」變化量", "變化量（口）", barmode="group",
            )

    st.divider()

    # 4. 融資餘額走勢
    st.subheader("💰 上市股票融資餘額走勢")
    st.caption("融資餘額增加，通常反映散戶（使用槓桿）追價意願提升；融資餘額減少則可能代表散戶信心轉弱或遭斷頭")
    with st.spinner("載入融資餘額趨勢中（首次載入需逐日查詢，請稍候）..."):
        df_margin = _fetch_margin_trend(n_days=20)
        if df_margin.empty:
            st.warning("目前無法取得融資餘額資料，請稍後再試。")
        else:
            latest_margin = df_margin.iloc[-1]
            if len(df_margin) >= 2:
                prev_margin = df_margin.iloc[-2]
                st.metric("融資餘額（仟元）", f"{int(latest_margin['融資餘額']):,}",
                          delta=f"{int(latest_margin['融資餘額'] - prev_margin['融資餘額']):,}（較前一日）")

            fig_margin = go.Figure()
            fig_margin.add_trace(go.Scatter(x=df_margin["日期"], y=df_margin["融資餘額"], name="融資餘額（仟元）", line=dict(color="green")))
            fig_margin.update_layout(title="上市股票融資餘額趨勢（近20個交易日）", xaxis_title="日期", yaxis_title="融資餘額（仟元）", hovermode="x unified")
            st.plotly_chart(fig_margin, use_container_width=True)

            render_diff_bar_chart(
                df_margin, "日期", [("融資餘額", "融資餘額較前一日變化")],
                "融資餘額「較前一日」變化量", "變化量（仟元）", color_by_sign=True,
            )

# ==================== 持股監控 ====================
elif page == "💼 持股監控":
    st.title("💼 持股監控")
    st_autorefresh(interval=5 * 60 * 1000, key="holdings_refresh")

    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(DATA_DIR, exist_ok=True)
    HOLDINGS_FILE = os.path.join(DATA_DIR, "holdings.csv")

    if os.path.exists(HOLDINGS_FILE):
        holdings = pd.read_csv(HOLDINGS_FILE, dtype={"證券代號": str})
    else:
        holdings = pd.DataFrame(columns=["證券代號"])

    with st.spinner("載入股票名稱中..."):
        name_map = {}
        try:
            url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json"
            res = requests.get(url, headers=MARKET_HEADERS, verify=False, timeout=15)
            data = res.json()
            df_price = pd.DataFrame(data["data"], columns=data["fields"])
            name_map.update(dict(zip(df_price["證券代號"], df_price["證券名稱"])))
        except Exception:
            pass

        try:
            url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
            res = requests.get(url, headers=MARKET_HEADERS, verify=False, timeout=15)
            data = res.json()
            for item in data:
                name_map.setdefault(item.get("SecuritiesCompanyCode", ""), item.get("CompanyName", ""))
        except Exception:
            pass

    left_col, right_col = st.columns([1, 1.5])

    with left_col:
        st.subheader("➕ 新增觀察股")
        with st.form("add_holding_form", clear_on_submit=True):
            new_id = st.text_input("股票代號（例如 2330）")
            submitted = st.form_submit_button("新增")

            if submitted:
                new_id = new_id.strip()
                if not new_id:
                    st.warning("請輸入股票代號")
                elif new_id not in name_map:
                    st.warning("查無股票代號")
                elif new_id in holdings["證券代號"].astype(str).values:
                    st.warning("此股票代號已存在")
                else:
                    holdings = pd.concat(
                        [holdings, pd.DataFrame([{"證券代號": new_id}])],
                        ignore_index=True,
                    )
                    holdings.to_csv(HOLDINGS_FILE, index=False, encoding="utf-8-sig")
                    st.success(f"已新增：{new_id}")
                    st.rerun()

        st.divider()

        if holdings.empty:
            st.info("👆 請於上方輸入股票代號後新增")
        else:
            st.subheader("📋 觀察名單")
            if "selected_stock" not in st.session_state and not holdings.empty:
                st.session_state["selected_stock"] = str(holdings.iloc[0]["證券代號"])
            for _, r in holdings.iterrows():
                sid = str(r["證券代號"])
                name = name_map.get(sid, "")
                label = f"{sid} {name}".strip()
                is_selected = st.session_state.get("selected_stock") == sid

                df_alert = fetch_stock_kline(sid, "1d", "6mo")
                alerts = check_stock_alerts(df_alert) if not df_alert.empty else []
                if alerts:
                    label = "🔔 " + label

                row_col1, row_col2 = st.columns([5, 1])
                with row_col1:
                    if st.button(("👉 " if is_selected else "") + label, key=f"select_{sid}", use_container_width=True):
                        st.session_state["selected_stock"] = sid
                        st.rerun()
                    if alerts:
                        st.caption("、".join(alerts))
                with row_col2:
                    if st.button("✕", key=f"delete_{sid}"):
                        holdings = holdings[holdings["證券代號"].astype(str) != sid].reset_index(drop=True)
                        holdings.to_csv(HOLDINGS_FILE, index=False, encoding="utf-8-sig")
                        if st.session_state.get("selected_stock") == sid:
                            st.session_state.pop("selected_stock", None)
                        st.rerun()

    with right_col:
        st.subheader("📈 K棒圖")
        if holdings.empty:
            st.info("請先於左側新增股票")
        else:
            KLINE_SCALES = {
                "1小時": ("60m", "1mo"),
                "日": ("1d", "6mo"),
                "週": ("1wk", "2y"),
                "月": ("1mo", "5y"),
            }
            kline_scale = st.selectbox("K棒時間尺度", list(KLINE_SCALES.keys()), index=1)
            kline_interval, kline_range = KLINE_SCALES[kline_scale]

            stock_ids = [str(r["證券代號"]) for _, r in holdings.iterrows()]
            stock_labels = [f"{s} {name_map.get(s, '')}".strip() for s in stock_ids]

            selected_sid = st.session_state.get("selected_stock", stock_ids[0])
            if selected_sid not in stock_ids:
                selected_sid = stock_ids[0]
            default_index = stock_ids.index(selected_sid)

            stock_choice = st.selectbox("選擇股票", stock_labels, index=default_index)
            sid = stock_ids[stock_labels.index(stock_choice)]
            st.session_state["selected_stock"] = sid
            name = name_map.get(sid, "")

            df_k = fetch_stock_kline(sid, kline_interval, kline_range)
            if df_k.empty:
                st.warning("無法取得K棒資料")
            else:
                if kline_interval == "60m":
                    times = (df_k["date"].astype("int64") // 10**9).tolist()
                else:
                    times = df_k["date"].dt.strftime("%Y-%m-%d").tolist()

                candle_data = [
                    {"time": t, "open": float(o), "high": float(h), "low": float(l), "close": float(c)}
                    for t, o, h, l, c in zip(times, df_k["open"], df_k["high"], df_k["low"], df_k["close"])
                ]
                volume_data = [
                    {"time": t, "value": float(v) if pd.notna(v) else 0,
                     "color": "rgba(239,83,80,0.5)" if c >= o else "rgba(38,166,154,0.5)"}
                    for t, v, o, c in zip(times, df_k["volume"], df_k["open"], df_k["close"])
                ]

                series_list = [
                    {
                        "type": "Candlestick",
                        "data": candle_data,
                        "options": {
                            "upColor": "#ef5350", "downColor": "#26a69a", "borderVisible": False,
                            "wickUpColor": "#ef5350", "wickDownColor": "#26a69a",
                        },
                    },
                    {
                        "type": "Histogram",
                        "data": volume_data,
                        "options": {"priceFormat": {"type": "volume"}, "priceScaleId": ""},
                        "priceScale": {"scaleMargins": {"top": 0.8, "bottom": 0}},
                    },
                ]

                if len(df_k) >= 5:
                    ma5_line = df_k["close"].rolling(5).mean()
                    series_list.append({
                        "type": "Line",
                        "data": [{"time": t, "value": round(float(v), 2)} for t, v in zip(times, ma5_line) if pd.notna(v)],
                        "options": {"color": "#FF9800", "lineWidth": 1, "title": "5MA"},
                    })
                if len(df_k) >= 20:
                    ma20_line = df_k["close"].rolling(20).mean()
                    series_list.append({
                        "type": "Line",
                        "data": [{"time": t, "value": round(float(v), 2)} for t, v in zip(times, ma20_line) if pd.notna(v)],
                        "options": {"color": "#2196F3", "lineWidth": 1, "title": "20MA"},
                    })

                for level_price, label, ltype in compute_support_resistance(df_k):
                    color = "#26a69a" if ltype == "support" else "#ef5350"
                    series_list.append({
                        "type": "Line",
                        "data": [
                            {"time": times[0], "value": round(float(level_price), 2)},
                            {"time": times[-1], "value": round(float(level_price), 2)},
                        ],
                        "options": {
                            "color": color, "lineWidth": 1, "lineStyle": 2,
                            "title": f"{label} {level_price:.2f}",
                        },
                    })

                chart_options = {
                    "height": 500,
                    "layout": {"textColor": "#333", "background": {"type": "solid", "color": "white"}},
                    "timeScale": {"timeVisible": kline_interval == "60m", "secondsVisible": False, "borderColor": "#ccc"},
                    "rightPriceScale": {"borderColor": "#ccc"},
                    "grid": {"vertLines": {"color": "rgba(220,220,220,0.5)"}, "horzLines": {"color": "rgba(220,220,220,0.5)"}},
                }

                st.caption(f"{sid} {name} K線圖（{kline_scale}）")
                renderLightweightCharts([{"chart": chart_options, "series": series_list}], key=f"kline_{sid}_{kline_scale}")