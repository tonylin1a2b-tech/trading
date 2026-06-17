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

#if not check_password():
#    st.stop()

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
def fetch_fedfunds_futures(range_="10d"):
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


@st.cache_data(ttl=60 * 30)
def fetch_sector_changes(sectors: dict) -> dict:
    """傳入 {名稱: Yahoo ticker} 字典，回傳 {名稱: 當日漲跌%} 字典。
    純數字代號自動嘗試 .TW → .TWO fallback。"""
    result = {}
    h = {"User-Agent": "Mozilla/5.0"}

    def _try_tickers(ticker):
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

    for name, ticker in sectors.items():
        for t in _try_tickers(ticker):
            try:
                r = requests.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?interval=1d&range=10d",
                    headers=h, verify=False, timeout=10,
                )
                data = r.json()
                if data.get("chart", {}).get("error"):
                    continue
                closes = [c for c in data["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c is not None]
                if len(closes) >= 2:
                    result[name] = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)
                    break
            except Exception:
                continue
    return result


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

    # 3. 選擇權 Put/Call Ratio（與前一日比較，比例上升偏空、下降偏多）
    try:
        df_pc = fetch_pc_ratio()
        if len(df_pc) >= 2:
            ratio = df_pc["買賣權未平倉量比率%"].iloc[-1]
            prev_ratio = df_pc["買賣權未平倉量比率%"].iloc[-2]
            if ratio > prev_ratio:
                scores["PC Ratio"] = -1
                details["PC Ratio"] = f"🔴 偏空（{_score_tag(-1)}）｜未平倉量 PC Ratio {ratio:.1f}%，較前一日 {prev_ratio:.1f}% 上升，賣權部位增加，避險氣氛升溫"
            elif ratio < prev_ratio:
                scores["PC Ratio"] = 1
                details["PC Ratio"] = f"🟢 偏多（{_score_tag(1)}）｜未平倉量 PC Ratio {ratio:.1f}%，較前一日 {prev_ratio:.1f}% 下降，買權部位增加，市場看多氣氛升溫"
            else:
                scores["PC Ratio"] = 0
                details["PC Ratio"] = f"🟡 中性（{_score_tag(0)}）｜未平倉量 PC Ratio {ratio:.1f}%，與前一日持平"
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
        df_ff = fetch_fedfunds_futures("10d")
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
page = st.sidebar.radio("選擇頁面", ["🏠 選股系統", "🌍 總經儀表板", "📰 新聞監控", "📊 散戶指標", "💼 持股監控", "📓 交易日記", "🌡️ 板塊熱力圖", "🔬 個股研究"])

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
    def get_dxy_history():
        url = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1d&range=3mo"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, verify=False, timeout=10)
        data = res.json()
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        df = pd.DataFrame({
            "date": pd.to_datetime([datetime.datetime.fromtimestamp(t) for t in timestamps]),
            "DXY": closes
        })
        return df.dropna().sort_values("date")

    st.subheader("💵 美元指數 DXY（近3個月）")
    with st.spinner("載入美元指數..."):
        try:
            df_dxy = get_dxy_history()
            latest_dxy = df_dxy["DXY"].iloc[-1]
            prev_dxy   = df_dxy["DXY"].iloc[-2]
            chg_dxy    = round(latest_dxy - prev_dxy, 3)
            pct_dxy    = round(chg_dxy / prev_dxy * 100, 2)
            sign       = "▲" if chg_dxy >= 0 else "▼"
            st.metric("DXY 最新", f"{latest_dxy:.3f}",
                      delta=f"{sign} {abs(chg_dxy):.3f} ({abs(pct_dxy):.2f}%)",
                      delta_color="normal" if chg_dxy >= 0 else "inverse")
            fig_dxy = go.Figure()
            fig_dxy.add_trace(go.Scatter(
                x=df_dxy["date"], y=df_dxy["DXY"],
                name="DXY", line=dict(color="#42a5f5", width=2),
                fill="tozeroy", fillcolor="rgba(66,165,245,0.08)",
            ))
            fig_dxy.update_layout(
                title="美元指數 (DXY) 近3個月走勢",
                xaxis_title="日期", yaxis_title="指數",
                hovermode="x unified",
                margin=dict(t=40, b=30),
            )
            st.plotly_chart(fig_dxy, use_container_width=True)
        except Exception as e:
            st.warning(f"美元指數暫時無法載入 ({e})")

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

                # 計算現價與漲跌幅
                price_text = ""
                price_color = "#888"
                if not df_alert.empty and len(df_alert) >= 2:
                    curr_close = df_alert["close"].iloc[-1]
                    prev_close = df_alert["close"].iloc[-2]
                    chg_pct = (curr_close - prev_close) / prev_close * 100
                    arrow = "▲" if chg_pct > 0 else ("▼" if chg_pct < 0 else "－")
                    price_color = "#ef5350" if chg_pct > 0 else ("#26a69a" if chg_pct < 0 else "#888")
                    price_text = f"{curr_close:.2f}　{arrow}{abs(chg_pct):.2f}%"

                row_col1, row_col2 = st.columns([5, 1])
                with row_col1:
                    if st.button(("👉 " if is_selected else "") + label, key=f"select_{sid}", use_container_width=True):
                        st.session_state["selected_stock"] = sid
                        st.rerun()
                    if price_text:
                        st.markdown(
                            f'<span style="font-size:0.92rem;font-weight:600;color:{price_color};padding-left:4px;">{price_text}</span>',
                            unsafe_allow_html=True,
                        )
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

# ==================== 交易日記 ====================
elif page == "📓 交易日記":
    st.title("📓 交易日記")

    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(DATA_DIR, exist_ok=True)
    TRADES_FILE = os.path.join(DATA_DIR, "trades.csv")
    CASH_FILE   = os.path.join(DATA_DIR, "cash.json")

    # 讀取交易紀錄
    TRADE_COLS = ["日期", "股票代號", "股票名稱", "交易類型", "方向", "數量", "單位", "價格", "手續費", "金額", "停損價", "停利價", "乘數", "報價代號", "原因", "衝動指數", "是否照計畫", "損益結果", "事後反思"]
    if os.path.exists(TRADES_FILE):
        df_trades = pd.read_csv(TRADES_FILE, dtype={"股票代號": str, "乘數": str, "報價代號": str})
        for c in TRADE_COLS:
            if c not in df_trades.columns:
                df_trades[c] = ""
    else:
        df_trades = pd.DataFrame(columns=TRADE_COLS)

    # 讀取現金與待交割
    _cash_file_data = {}
    if os.path.exists(CASH_FILE):
        with open(CASH_FILE, "r", encoding="utf-8") as f:
            _cash_file_data = json.load(f)
    cash_balance = float(_cash_file_data.get("cash", 0))

    # ── 資產總覽 ───────────────────────────────────────
    st.subheader("💰 資產總覽")

    # 從交易紀錄算出淨持倉，再抓 Yahoo Finance 現價
    holdings_mkt = 0.0
    holdings_detail = []
    if not df_trades.empty:
        # 只計算現股/零股/融資（期貨不計入市值）
        df_pos = df_trades[df_trades["交易類型"].astype(str).isin(["現股", "零股", "融資"])].copy()
        df_pos["數量_n"] = pd.to_numeric(df_pos["數量"].fillna(df_pos.get("股數", 0)), errors="coerce").fillna(0)
        df_pos["單位_n"] = df_pos["單位"].astype(str).fillna("張")
        # 買為正、賣為負
        df_pos["淨數量"] = df_pos.apply(
            lambda r: r["數量_n"] if str(r.get("方向","")) == "買" else -r["數量_n"], axis=1
        )
        # 張轉股
        def _to_shares(row):
            u = str(row.get("單位_n", "張"))
            n = row["淨數量"]
            return n * 1000 if u in ("張", "") else n  # 零股直接用股數
        df_pos["股數"] = df_pos.apply(_to_shares, axis=1)
        net_pos = df_pos.groupby("股票代號")["股數"].sum()
        net_pos = net_pos[net_pos > 0]

        for sid_h, shares_h in net_pos.items():
            ticker_yf = f"{sid_h}.TW"
            try:
                r = requests.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_yf}?interval=1d&range=5d",
                    headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=8
                )
                closes = r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
                curr = next((c for c in reversed(closes) if c is not None), None)
                if curr:
                    mval = curr * shares_h
                    holdings_mkt += mval
                    holdings_detail.append({
                        "代號": sid_h, "持股(股)": int(shares_h),
                        "現價": round(curr, 2), "市值": round(mval, 0)
                    })
            except Exception:
                pass

    # 讀取手動輸入的待交割金額
    settlement_t1 = float(_cash_file_data.get("t1", 0))
    settlement_t2 = float(_cash_file_data.get("t2", 0))

    pending_net = settlement_t1 + settlement_t2  # 正=將收入，負=將支出

    # ── 期貨未實現損益 ─────────────────────────────────
    futures_pnl = 0.0
    futures_detail = []
    if not df_trades.empty:
        df_fut = df_trades[df_trades["交易類型"].astype(str) == "期貨"].copy()
        if not df_fut.empty:
            df_fut["數量_n"] = pd.to_numeric(df_fut["數量"].fillna(0), errors="coerce").fillna(0)
            df_fut["淨口"] = df_fut.apply(
                lambda r: r["數量_n"] if str(r.get("方向","")) == "買" else -r["數量_n"], axis=1
            )
            df_fut["價格_n"] = pd.to_numeric(df_fut["價格"], errors="coerce").fillna(0)
            df_fut["乘數_n"] = pd.to_numeric(df_fut.get("乘數", 200), errors="coerce").fillna(200)
            # 報價代號為空時自動補 {股票代號}.TW
            def _resolve_qticker(row):
                qt = str(row.get("報價代號", "")).strip()
                if not qt or qt == "nan":
                    sid = str(row.get("股票代號", "")).strip()
                    return f"{sid}.TW" if sid else ""
                return qt
            df_fut["報價代號_s"] = df_fut.apply(_resolve_qticker, axis=1)

            # 用 (報價代號, 股票代號) 做群組，同一商品可能有不同代號填法
            df_fut["_group_key"] = df_fut.apply(
                lambda r: r["報價代號_s"] or str(r.get("股票代號","")), axis=1
            )

            for gkey, grp in df_fut.groupby("_group_key"):
                if not gkey or gkey == "nan":
                    continue
                net_lots = grp["淨口"].sum()
                mult = pd.to_numeric(grp["乘數_n"].replace("", float("nan")), errors="coerce").dropna()
                mult = float(mult.iloc[-1]) if not mult.empty else 200.0

                buy_g  = grp[grp["淨口"] > 0]
                sell_g = grp[grp["淨口"] < 0]
                if net_lots > 0 and not buy_g.empty:
                    avg_entry = (buy_g["價格_n"] * buy_g["淨口"]).sum() / buy_g["淨口"].sum()
                elif net_lots < 0 and not sell_g.empty:
                    avg_entry = (sell_g["價格_n"] * abs(sell_g["淨口"])).sum() / abs(sell_g["淨口"]).sum()
                else:
                    avg_entry = 0

                qticker   = grp["報價代號_s"].iloc[-1] or gkey
                sid_label = str(grp["股票代號"].iloc[0])

                # 抓現價
                curr_price = None
                try:
                    r = requests.get(
                        f"https://query1.finance.yahoo.com/v8/finance/chart/{qticker}?interval=1d&range=5d",
                        headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=8
                    )
                    closes = r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
                    curr_price = next((c for c in reversed(closes) if c is not None), None)
                except Exception:
                    pass

                if net_lots == 0:
                    futures_detail.append({
                        "代號": sid_label, "報價代號": qticker,
                        "淨口數": 0, "乘數": int(mult),
                        "均價": round(avg_entry, 2),
                        "現價": round(curr_price, 2) if curr_price else "—",
                        "未實現損益": 0,
                    })
                elif curr_price:
                    pnl = (curr_price - avg_entry) * net_lots * mult
                    futures_pnl += pnl
                    futures_detail.append({
                        "代號": sid_label, "報價代號": qticker,
                        "淨口數": int(net_lots), "乘數": int(mult),
                        "均價": round(avg_entry, 2), "現價": round(curr_price, 2),
                        "未實現損益": round(pnl, 0),
                    })
                else:
                    futures_detail.append({
                        "代號": sid_label, "報價代號": qticker,
                        "淨口數": int(net_lots), "乘數": int(mult),
                        "均價": round(avg_entry, 2), "現價": "無法取得",
                        "未實現損益": "—",
                    })

    total_assets = cash_balance + holdings_mkt + futures_pnl
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("現金", f"${cash_balance:,.0f}")
    a2.metric("持股市值", f"${holdings_mkt:,.0f}")
    a3.metric("期貨損益", f"{'＋' if futures_pnl >= 0 else '－'}${abs(futures_pnl):,.0f}",
              delta_color="off", delta="未實現")
    a4.metric("總資產", f"${total_assets:,.0f}")

    if holdings_detail:
        with st.expander("📊 持股明細", expanded=True):
            st.dataframe(
                pd.DataFrame(holdings_detail).set_index("代號")
                .style.format({"現價": "{:.2f}", "市值": "{:,.0f}", "持股(股)": "{:,.0f}"}),
                use_container_width=True,
            )

    if futures_detail:
        with st.expander("📈 期貨部位明細", expanded=True):
            df_fd = pd.DataFrame(futures_detail).set_index("代號")
            def _color_pnl_fut(v):
                try:
                    return "color:#ef5350;font-weight:600" if float(v) < 0 else "color:#26a69a;font-weight:600"
                except Exception:
                    return ""
            st.dataframe(df_fd.style.map(_color_pnl_fut, subset=["未實現損益"]),
                         use_container_width=True)

    b1, b2, b3 = st.columns(3)
    b1.metric("待交割 T+1", f"{'＋' if settlement_t1 >= 0 else '－'}${abs(settlement_t1):,.0f}", delta="正=收入 負=付出", delta_color="off")
    b2.metric("待交割 T+2", f"{'＋' if settlement_t2 >= 0 else '－'}${abs(settlement_t2):,.0f}", delta="正=收入 負=付出", delta_color="off")
    b3.metric(
        "待交割淨額",
        f"{'＋' if pending_net >= 0 else '－'}${abs(pending_net):,.0f}",
        delta="正=將收入 負=將付出",
        delta_color="off",
    )

    # 現金 / 待交割調整
    with st.expander("✏️ 更新現金與待交割", expanded=False):
        _cf1, _cf2, _cf3 = st.columns(3)
        new_cash = _cf1.number_input("現金餘額（元）", value=cash_balance, step=1000.0, format="%.0f")
        new_t1   = _cf2.number_input("T+1 待交割（正=收入 負=付出）", value=settlement_t1, step=1000.0, format="%.0f")
        new_t2   = _cf3.number_input("T+2 待交割（正=收入 負=付出）", value=settlement_t2, step=1000.0, format="%.0f")
        if st.button("儲存"):
            _cash_data = {}
            if os.path.exists(CASH_FILE):
                with open(CASH_FILE, "r", encoding="utf-8") as f:
                    _cash_data = json.load(f)
            _cash_data.update({"cash": new_cash, "t1": new_t1, "t2": new_t2})
            with open(CASH_FILE, "w", encoding="utf-8") as f:
                json.dump(_cash_data, f)
            st.rerun()

    # ── 交易紀錄統計 ───────────────────────────────────
    st.divider()
    total_trades = len(df_trades)
    if total_trades > 0:
        follow_yes = (df_trades["是否照計畫"].astype(str) == "完全照做").sum()
        follow_rate = round(follow_yes / total_trades * 100)
        emotion_vals = pd.to_numeric(df_trades["衝動指數"], errors="coerce").dropna()
        avg_emotion = round(emotion_vals.mean(), 1) if len(emotion_vals) > 0 else 0
        now_ym = datetime.date.today().strftime("%Y-%m")
        month_count = df_trades[df_trades["日期"].astype(str).str[:7] == now_ym].shape[0]
    else:
        follow_rate = avg_emotion = month_count = 0

    _s1, _s2, _s3, _s4 = st.columns(4)
    _s1.metric("紀錄筆數", total_trades)
    _s2.metric("守規率", f"{follow_rate}%" if total_trades else "—")
    _s3.metric("平均衝動指數", f"{avg_emotion}/10" if total_trades else "—")
    _s4.metric("本月交易", month_count if total_trades else "—")

    st.divider()

    # ── 新增交易紀錄 ───────────────────────────────────
    st.subheader("➕ 新增交易")
    with st.container(border=True):
        r1c1, r1c2, r1c3, r1c4 = st.columns([1.2, 1.2, 1, 1])
        t_date  = r1c1.date_input("日期", value=datetime.date.today(), key="t_date")
        t_sid   = r1c2.text_input("股票代號／商品", key="t_sid", placeholder="例如 2330 / TXFA5")
        t_type  = r1c3.selectbox("交易類型", ["現股", "零股", "融資", "期貨"], key="t_type")
        t_dir   = r1c4.selectbox("方向", ["買", "賣"], key="t_dir")

        # 單位依交易類型動態切換
        _unit_map = {"現股": "張", "零股": "股", "融資": "張", "期貨": "口"}
        _unit = _unit_map[t_type]
        _qty_min = 1

        r2c1, r2c2, r2c3 = st.columns([1, 1, 1])
        t_shares = r2c1.number_input(f"數量（{_unit}）", min_value=_qty_min, value=1, step=1, key="t_shares")
        t_price  = r2c2.number_input("價格／指數點位", min_value=0.0, value=100.0, step=0.01, key="t_price", format="%.2f")
        t_fee    = r2c3.number_input("手續費／稅", min_value=0, value=0, step=1, key="t_fee")

        if t_type == "期貨":
            _fu1, _fu2 = st.columns(2)
            _default_mult = {"大台": 200, "小台": 50, "股票期貨": 2000}.get("大台", 200)
            t_mult    = _fu1.number_input("每口乘數（元/點）", min_value=1, value=200, step=1, key="t_mult",
                                          help="大台=200、小台=50、個股期貨=2000")
            t_quote_ticker = _fu2.text_input("報價代號（抓現價用）", key="t_qticker",
                                             placeholder="大台→^TWII，個股期→2330.TW")
        else:
            t_mult = 1
            t_quote_ticker = ""

        _sl_col, _tp_col = st.columns(2)
        t_sl = _sl_col.number_input("預期停損價", min_value=0.0, value=0.0, step=0.01, format="%.2f", key="t_sl", help="設為 0 表示未設定")
        t_tp = _tp_col.number_input("預期停利價", min_value=0.0, value=0.0, step=0.01, format="%.2f", key="t_tp", help="設為 0 表示未設定")

        t_reason = st.text_area("進出場理由", key="t_reason", placeholder="根據什麼條件做這個決定？技術面、基本面、消息、還是單純感覺？", height=80)

        _em_col, _fp_col, _res_col = st.columns([1.5, 1.5, 1])
        t_emotion = _em_col.slider("衝動指數（0=冷靜，10=衝動）", min_value=0, max_value=10, value=5, key="t_emotion")
        t_follow  = _fp_col.selectbox("是否照計畫執行", ["完全照做", "部分照做", "沒有照做"], key="t_follow")
        t_result  = _res_col.number_input("損益結果（可事後補）", value=0.0, step=100.0, format="%.0f", key="t_result")

        # 衝動指數視覺提示
        _em_tier = "🟢 冷靜" if t_emotion <= 3 else ("🟡 警戒" if t_emotion <= 6 else "🔴 衝動")
        _em_color = "#26a69a" if t_emotion <= 3 else ("#f5a623" if t_emotion <= 6 else "#ef5350")
        st.markdown(f'<span style="font-size:0.9rem;font-weight:600;color:{_em_color}">{_em_tier}（{t_emotion}/10）</span>', unsafe_allow_html=True)

        t_reflection = st.text_area("事後反思（可事後補）", key="t_reflection", placeholder="如果重來一次，會不會做一樣的決定？", height=70)

        if st.button("➕ 新增這筆", type="primary"):
            sid = t_sid.strip()
            if not sid:
                st.warning("請輸入股票代號")
            else:
                sname = ""
                try:
                    url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json"
                    res = requests.get(url, headers=MARKET_HEADERS, verify=False, timeout=10)
                    tmp = pd.DataFrame(res.json()["data"], columns=res.json()["fields"])
                    row_s = tmp[tmp["證券代號"] == sid]
                    if not row_s.empty:
                        sname = row_s.iloc[0]["證券名稱"]
                except Exception:
                    pass

                # 金額計算
                if t_type == "現股" or t_type == "融資":
                    notional = t_price * t_shares * 1000
                elif t_type == "零股":
                    notional = t_price * t_shares
                else:  # 期貨
                    notional = t_price * t_shares * 200  # 大台每點200元，可自行修改
                fee_sign = t_fee if t_dir == "買" else -t_fee
                amount = notional + fee_sign
                new_trade = pd.DataFrame([{
                    "日期": str(t_date), "股票代號": sid, "股票名稱": sname,
                    "交易類型": t_type,
                    "方向": t_dir, "數量": t_shares, "單位": _unit, "價格": t_price,
                    "手續費": t_fee,
                    "金額": round(-amount if t_dir == "買" else amount, 0),
                    "停損價": t_sl if t_sl > 0 else None,
                    "停利價": t_tp if t_tp > 0 else None,
                    "乘數": str(t_mult) if t_type == "期貨" else "",
                    "報價代號": t_quote_ticker.strip() if t_type == "期貨" else "",
                    "原因": t_reason.strip(),
                    "衝動指數": t_emotion,
                    "是否照計畫": t_follow,
                    "損益結果": t_result if t_result != 0.0 else None,
                    "事後反思": t_reflection.strip(),
                }])
                df_trades = pd.concat([df_trades, new_trade], ignore_index=True)
                df_trades = df_trades.sort_values("日期", ascending=False).reset_index(drop=True)
                df_trades.to_csv(TRADES_FILE, index=False, encoding="utf-8-sig")
                st.success(f"已新增：{t_type} {t_dir} {sid} {t_shares}{_unit} @ {t_price}")
                st.rerun()

    st.divider()

    # ── 交易紀錄卡片 ───────────────────────────────────
    st.subheader("📋 交易紀錄")
    if df_trades.empty:
        st.info("尚無交易紀錄，請於上方新增")
    else:
        _filter = st.text_input("🔍 依股票代號篩選", placeholder="例如 2330", key="trade_filter")
        df_show = df_trades.sort_values("日期", ascending=False).reset_index(drop=True)
        if _filter.strip():
            df_show = df_show[df_show["股票代號"].astype(str).str.contains(_filter.strip())]

        def _follow_color(v):
            return {"完全照做": "#5C8A76", "部分照做": "#C99A3F", "沒有照做": "#B6543D"}.get(str(v), "#888")
        def _follow_border(v):
            return {"完全照做": "#5C8A76", "部分照做": "#C99A3F", "沒有照做": "#B6543D"}.get(str(v), "#888")
        def _emotion_color(v):
            try:
                ev = int(v)
                return "#5C8A76" if ev <= 3 else ("#C99A3F" if ev <= 6 else "#B6543D")
            except Exception:
                return "#888"

        _type_colors = {"現股": "#4a7fa5", "零股": "#7a5fa5", "融資": "#c99a3f", "期貨": "#b6543d"}
        _unit_map = {"現股": "張", "零股": "股", "融資": "張", "期貨": "口"}

        for idx, row in df_show.iterrows():
            follow_val = str(row.get("是否照計畫", ""))
            border_c = _follow_border(follow_val)
            dir_label = "買進" if str(row.get("方向", "")) == "買" else "賣出"
            dir_color = "#ef5350" if str(row.get("方向", "")) == "買" else "#26a69a"
            emotion_v = row.get("衝動指數", "")
            result_v  = row.get("損益結果", "")
            reason_v  = str(row.get("原因", "")).strip()
            reflect_v = str(row.get("事後反思", "")).strip()
            sname_v   = str(row.get("股票名稱", "")).strip()
            ttype_v   = str(row.get("交易類型", "")).strip()
            qty_v     = row.get("數量", row.get("股數", ""))
            unit_v    = str(row.get("單位", "張")).strip()
            if unit_v in ("", "nan"):
                unit_v = "張"

            sl_v = str(row.get("停損價", "")).strip()
            tp_v = str(row.get("停利價", "")).strip()

            type_badge = f'<span style="background:{_type_colors.get(ttype_v,"#888")};color:#fff;font-size:11px;padding:2px 8px;border-radius:10px;font-family:monospace">{ttype_v}</span>' if ttype_v and ttype_v != "nan" else ""
            try:
                result_num = float(result_v)
                result_badge = f'<span style="background:{"#5C8A76" if result_num>=0 else "#B6543D"};color:#fff;font-size:11px;padding:2px 8px;border-radius:10px;font-family:monospace">{"+" if result_num>=0 else ""}{result_num:,.0f}</span>'
            except Exception:
                result_badge = ""
            follow_badge = f'<span style="background:{_follow_color(follow_val)};color:#fff;font-size:11px;padding:2px 8px;border-radius:10px;font-family:monospace">{follow_val or "—"}</span>' if follow_val and follow_val != "nan" else ""
            emotion_badge = f'<span style="background:{_emotion_color(emotion_v)};color:#fff;font-size:11px;padding:2px 8px;border-radius:10px;font-family:monospace">衝動指數 {emotion_v}/10</span>' if str(emotion_v).strip() not in ("", "nan") else ""
            sl_line = f'<span style="font-family:monospace;font-size:12px;color:#B6543D">停損 {sl_v}</span>' if sl_v and sl_v != "nan" else ""
            tp_line = f'<span style="font-family:monospace;font-size:12px;color:#5C8A76">停利 {tp_v}</span>' if tp_v and tp_v != "nan" else ""
            sltp_row = f'<div style="margin-top:5px;display:flex;gap:14px">{sl_line}{tp_line}</div>' if sl_line or tp_line else ""

            card_html = f"""
<div style="background:#f9f6ef;border-left:5px solid {border_c};border-radius:6px;padding:14px 16px;margin-bottom:4px;color:#20262E">
  <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px">
    <div style="font-family:monospace;font-size:14px;font-weight:700">{row.get('股票代號','')} {sname_v} · <span style="color:{dir_color}">{dir_label}</span></div>
    <div style="font-family:monospace;font-size:12px;color:#5B6573">{row.get('日期','')} ・ {row.get('價格','')} × {qty_v}{unit_v}</div>
  </div>
  <div style="margin-top:7px;display:flex;gap:6px;flex-wrap:wrap">{type_badge}{follow_badge}{emotion_badge}{result_badge}</div>
  {sltp_row}
  {"<div style='font-size:13px;margin-top:8px;line-height:1.6'>" + reason_v + "</div>" if reason_v and reason_v != "nan" else ""}
  {"<div style='font-size:12px;color:#5B6573;margin-top:6px;font-style:italic;line-height:1.5'>反思：" + reflect_v + "</div>" if reflect_v and reflect_v != "nan" else ""}
</div>"""
            st.markdown(card_html, unsafe_allow_html=True)

            # 編輯 / 刪除按鈕
            _ba, _bb, _bc = st.columns([1, 1, 8])
            if _ba.button("✏️ 編輯", key=f"edit_{idx}"):
                st.session_state["editing_trade"] = idx
                st.rerun()
            if _bb.button("🗑️", key=f"del_{idx}"):
                df_trades = df_trades.drop(index=idx).reset_index(drop=True)
                df_trades.to_csv(TRADES_FILE, index=False, encoding="utf-8-sig")
                st.rerun()

            # 編輯表單（展開在當筆下方）
            if st.session_state.get("editing_trade") == idx:
                with st.container(border=True):
                    st.caption("✏️ 編輯這筆紀錄")
                    _safe_str = lambda k, d="": str(row.get(k, d)) if str(row.get(k, d)) not in ("nan", "") else d
                    _safe_float = lambda k, d=0.0: float(row[k]) if pd.notna(row.get(k)) and str(row.get(k)) not in ("", "nan") else d
                    _safe_int = lambda k, d=0: int(float(row[k])) if pd.notna(row.get(k)) and str(row.get(k)) not in ("", "nan") else d

                    ec1, ec2, ec3, ec4 = st.columns([1.2, 1.2, 1, 1])
                    try:
                        _edate = datetime.date.fromisoformat(_safe_str("日期", str(datetime.date.today())))
                    except Exception:
                        _edate = datetime.date.today()
                    e_date   = ec1.date_input("日期", value=_edate, key=f"e_date_{idx}")
                    e_sid    = ec2.text_input("股票代號", value=_safe_str("股票代號"), key=f"e_sid_{idx}")
                    _etype_opts = ["現股", "零股", "融資", "期貨"]
                    _etype_def  = _safe_str("交易類型", "現股")
                    e_type   = ec3.selectbox("交易類型", _etype_opts, index=_etype_opts.index(_etype_def) if _etype_def in _etype_opts else 0, key=f"e_type_{idx}")
                    _edir_opts = ["買", "賣"]
                    _edir_def  = _safe_str("方向", "買")
                    e_dir    = ec4.selectbox("方向", _edir_opts, index=_edir_opts.index(_edir_def) if _edir_def in _edir_opts else 0, key=f"e_dir_{idx}")

                    er1, er2, er3 = st.columns([1, 1, 1])
                    _e_unit = _unit_map.get(e_type, "張")
                    _e_qty_raw = row.get("數量", row.get("股數", 1))
                    _e_qty = int(float(_e_qty_raw)) if pd.notna(_e_qty_raw) and str(_e_qty_raw) not in ("", "nan") else 1
                    e_qty    = er1.number_input(f"數量（{_e_unit}）", min_value=1, value=max(1, _e_qty), step=1, key=f"e_qty_{idx}")
                    e_price  = er2.number_input("價格", min_value=0.0, value=_safe_float("價格", 100.0), step=0.01, format="%.2f", key=f"e_price_{idx}")
                    e_fee    = er3.number_input("手續費／稅", min_value=0, value=_safe_int("手續費"), step=1, key=f"e_fee_{idx}")

                    _esl_col, _etp_col = st.columns(2)
                    e_sl = _esl_col.number_input("預期停損價", min_value=0.0, value=_safe_float("停損價", 0.0), step=0.01, format="%.2f", key=f"e_sl_{idx}")
                    e_tp = _etp_col.number_input("預期停利價", min_value=0.0, value=_safe_float("停利價", 0.0), step=0.01, format="%.2f", key=f"e_tp_{idx}")

                    if str(row.get("交易類型","")) == "期貨":
                        _em1, _em2 = st.columns(2)
                        e_mult   = _em1.number_input("每口乘數", min_value=1, value=_safe_int("乘數", 200), step=1, key=f"e_mult_{idx}")
                        e_qticker = _em2.text_input("報價代號", value=_safe_str("報價代號"), key=f"e_qticker_{idx}")
                    else:
                        e_mult = 1
                        e_qticker = ""

                    e_reason   = st.text_area("進出場理由", value=_safe_str("原因"), key=f"e_reason_{idx}", height=70)
                    _e_em_def  = _safe_int("衝動指數", 5)
                    _efl_opts  = ["完全照做", "部分照做", "沒有照做"]
                    _efl_def   = _safe_str("是否照計畫", "完全照做")
                    ef1, ef2, ef3 = st.columns([1.5, 1.5, 1])
                    e_emotion  = ef1.slider("衝動指數", 0, 10, value=min(10, max(0, _e_em_def)), key=f"e_em_{idx}")
                    e_follow   = ef2.selectbox("是否照計畫", _efl_opts, index=_efl_opts.index(_efl_def) if _efl_def in _efl_opts else 0, key=f"e_fp_{idx}")
                    e_result   = ef3.number_input("損益結果", value=_safe_float("損益結果", 0.0), step=100.0, format="%.0f", key=f"e_res_{idx}")
                    e_reflect  = st.text_area("事後反思", value=_safe_str("事後反思"), key=f"e_rf_{idx}", height=60)

                    _sb, _cb = st.columns([1, 1])
                    if _sb.button("💾 儲存修改", type="primary", key=f"e_save_{idx}"):
                        if e_type in ("現股", "融資"):
                            notional = e_price * e_qty * 1000
                        elif e_type == "零股":
                            notional = e_price * e_qty
                        else:
                            notional = e_price * e_qty * 200
                        fee_sign = e_fee if e_dir == "買" else -e_fee
                        e_amount = round(-(notional + fee_sign) if e_dir == "買" else (notional - fee_sign), 0)
                        df_trades.loc[idx, "日期"]      = str(e_date)
                        df_trades.loc[idx, "股票代號"]   = e_sid.strip()
                        df_trades.loc[idx, "交易類型"]   = e_type
                        df_trades.loc[idx, "方向"]       = e_dir
                        df_trades.loc[idx, "數量"]       = e_qty
                        df_trades.loc[idx, "單位"]       = _e_unit
                        df_trades.loc[idx, "價格"]       = e_price
                        df_trades.loc[idx, "手續費"]     = e_fee
                        df_trades.loc[idx, "金額"]       = e_amount
                        df_trades.loc[idx, "停損價"]     = e_sl if e_sl > 0 else None
                        df_trades.loc[idx, "停利價"]     = e_tp if e_tp > 0 else None
                        df_trades.loc[idx, "乘數"]       = str(e_mult) if str(row.get("交易類型","")) == "期貨" else ""
                        df_trades.loc[idx, "報價代號"]   = e_qticker.strip()
                        df_trades.loc[idx, "原因"]       = e_reason.strip()
                        df_trades.loc[idx, "衝動指數"]   = e_emotion
                        df_trades.loc[idx, "是否照計畫"] = e_follow
                        df_trades.loc[idx, "損益結果"]   = e_result if e_result != 0.0 else None
                        df_trades.loc[idx, "事後反思"]   = e_reflect.strip()
                        df_trades.to_csv(TRADES_FILE, index=False, encoding="utf-8-sig")
                        st.session_state.pop("editing_trade", None)
                        st.rerun()
                    if _cb.button("取消", key=f"e_cancel_{idx}"):
                        st.session_state.pop("editing_trade", None)
                        st.rerun()

            st.markdown("<div style='margin-bottom:6px'></div>", unsafe_allow_html=True)

# ==================== 板塊熱力圖 ====================
elif page == "🌡️ 板塊熱力圖":
    st.title("🌡️ 板塊熱力圖")
    st.caption("點擊分類格進入細項，點擊左上角返回。每30分鐘更新一次。")

    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(DATA_DIR, exist_ok=True)
    SECTOR_CFG = os.path.join(DATA_DIR, "sector_config.json")

    # 兩層巢狀格式：{群組: {分類: {名稱: ticker}}}
    # 也支援舊格式（平面）：{群組: {名稱: ticker}}
    DEFAULT_CFG = {
        "🇹🇼 台股": {
            "晶圓代工": {"台積電":"2330.TW","聯電":"2303.TW"},
            "IC設計":   {"聯發科":"2454.TW","瑞昱":"2379.TW","聯詠":"3034.TW"},
            "封測":     {"日月光":"3711.TW"},
            "DRAM":     {"南亞科":"2408.TW","華邦電":"2344.TW"},
            "Flash":    {"旺宏":"2337.TW","群聯":"8299.TW"},
            "載板":     {"欣興":"3037.TW","南電":"8046.TW"},
            "PCB":      {"健鼎":"3044.TW"},
            "CCL":      {"台光電":"2383.TW"},
            "電源管理": {"台達電":"2308.TW","光寶科":"2301.TW"},
            "被動元件": {"國巨":"2327.TW","華新科":"2492.TW"},
            "連接器":   {"正崴":"2392.TW","嘉澤":"3533.TW"},
            "散熱":     {"奇鋐":"3017.TW","雙鴻":"3324.TW","建準":"2421.TW"},
            "伺服器/EMS":{"廣達":"2382.TW","緯穎":"6669.TW","緯創":"3231.TW","英業達":"2356.TW","鴻海":"2317.TW","仁寶":"2324.TW","和碩":"4938.TW"},
            "網通":     {"智邦":"2345.TW"},
            "石化":     {"台塑":"1301.TW","南亞":"1303.TW","台化":"1326.TW","台塑化":"6505.TW"},
            "電信":     {"中華電":"2412.TW","台灣大":"3045.TW","遠傳":"4904.TW"},
            "航運":     {"長榮":"2603.TW","陽明":"2609.TW","萬海":"2615.TW"},
            "鋼鐵":     {"中鋼":"2002.TW"},
            "食品/零售":{"統一":"1216.TW","統一超":"2912.TW"},
            "金融":     {"富邦金":"2881.TW","國泰金":"2882.TW","中信金":"2891.TW","兆豐金":"2886.TW","玉山金":"2884.TW","第一金":"2892.TW"},
        },
        "🇺🇸 美股": {
            "科技":      {"Microsoft":"MSFT","Apple":"AAPL","NVIDIA":"NVDA","Google":"GOOGL","Meta":"META","Netflix":"NFLX","Oracle":"ORCL","Salesforce":"CRM","Adobe":"ADBE","ServiceNow":"NOW"},
            "半導體":    {"AMD":"AMD","Broadcom":"AVGO","Qualcomm":"QCOM","TSMC ADR":"TSM","ARM":"ARM","Marvell":"MRVL","Micron":"MU","Intel":"INTC"},
            "半導體設備":{"Applied Materials":"AMAT","Lam Research":"LRCX","KLA":"KLAC","ASML":"ASML"},
            "AI基礎建設":{"SMCI":"SMCI","Dell":"DELL","Vertiv":"VRT","Arista":"ANET","Amphenol":"APH"},
            "電商/消費": {"Amazon":"AMZN","Tesla":"TSLA","Walmart":"WMT","Costco":"COST","McDonald's":"MCD","Nike":"NKE","Starbucks":"SBUX"},
            "消費品":    {"Coca-Cola":"KO","P&G":"PG","PepsiCo":"PEP","J&J":"JNJ"},
            "金融":      {"JPMorgan":"JPM","Goldman":"GS","BofA":"BAC","Morgan Stanley":"MS","Visa":"V","Mastercard":"MA","Berkshire":"BRK-B","AmEx":"AXP"},
            "醫療":      {"Eli Lilly":"LLY","UnitedHealth":"UNH","AbbVie":"ABBV","Merck":"MRK","Amgen":"AMGN","Pfizer":"PFE","Thermo Fisher":"TMO"},
            "能源":      {"ExxonMobil":"XOM","Chevron":"CVX","ConocoPhillips":"COP","Occidental":"OXY"},
            "工業":      {"Caterpillar":"CAT","RTX":"RTX","Lockheed":"LMT","Honeywell":"HON","GE":"GE","Deere":"DE","UPS":"UPS"},
            "電信":      {"AT&T":"T","Verizon":"VZ","T-Mobile":"TMUS"},
        },
        "🇯🇵 日股": {
            "半導體":    {"東京威力科創":"8035.T","Lasertec":"6920.T","Renesas":"6723.T","信越化學":"4063.T","ROHM":"6963.T"},
            "電子零件":  {"Alps Alpine":"6770.T"},
            "被動元件":  {"村田製作所":"6981.T","TDK":"6762.T","太陽誘電":"6976.T","Kyocera":"6971.T"},
            "精密/FA":   {"Keyence":"6861.T","Fanuc":"6954.T","安川電機":"6506.T","Nidec":"6594.T"},
            "消費電子":  {"索尼":"6758.T","Canon":"7751.T","Panasonic":"6752.T"},
            "汽車":      {"Toyota":"7203.T","Honda":"7267.T","Denso":"6902.T","Subaru":"7270.T"},
            "製藥":      {"Takeda":"4502.T","Daiichi Sankyo":"4568.T","Astellas":"4503.T"},
            "零售":      {"Fast Retailing":"9983.T","Seven & i":"3382.T"},
            "食品":      {"Asahi":"2502.T","Kirin":"2503.T"},
            "不動産":    {"三井不動産":"8801.T","三菱地所":"8802.T"},
            "航運":      {"NYK":"9101.T","Mitsui OSK":"9104.T"},
            "金融":      {"三菱UFJ":"8306.T","三井住友":"8316.T","瑞穗":"8411.T"},
            "遊戲/娛樂": {"Nintendo":"7974.T","Capcom":"9697.T","Konami":"9766.T","Square Enix":"9684.T"},
            "載板":      {"Ibiden":"4062.T","Shinko Electric":"6967.T","Toppan":"7911.T"},
            "石英":      {"日本電波工業":"6779.T","Seiko Epson":"6724.T","大真空":"6962.T"},
        },
    }

    if os.path.exists(SECTOR_CFG):
        with open(SECTOR_CFG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        cfg = DEFAULT_CFG

    def _is_nested(group_val: dict) -> bool:
        """判斷群組值是否為巢狀格式（值為 dict）或平面格式（值為 str）"""
        return any(isinstance(v, dict) for v in group_val.values())

    @st.cache_data(ttl=60 * 30)
    def fetch_nested_changes(flat_tickers: tuple) -> dict:
        """接收 ((名稱, ticker), ...) tuple，回傳 {名稱: (price, chg%)}
        若 ticker 是純數字，自動嘗試 .TW → .TWO fallback"""
        result = {}
        h = {"User-Agent": "Mozilla/5.0"}

        def _fetch_closes(ticker):
            r = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=10d",
                headers=h, verify=False, timeout=10
            )
            data = r.json()
            if data.get("chart", {}).get("error"):
                return None
            closes = [c for c in data["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c is not None]
            return closes if len(closes) >= 2 else None

        def _auto_ticker(ticker):
            """根據後綴決定嘗試順序"""
            if ticker.endswith(".TW"):
                return [ticker, ticker[:-3] + ".TWO"]
            elif ticker.endswith(".TWO"):
                return [ticker, ticker[:-4] + ".TW"]
            elif ticker.endswith(".T"):
                return [ticker]          # 日股，直接用
            else:
                return [ticker]          # 美股等，直接用

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
                chg   = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)
                result[name] = (round(price, 2), chg)
        return result

    CSCALE = [
        [0.0,  "#1b5e20"],
        [0.25, "#43a047"],
        [0.42, "#a5d6a7"],
        [0.5,  "#eceff1"],
        [0.58, "#ef9a9a"],
        [0.75, "#e53935"],
        [1.0,  "#b71c1c"],
    ]

    def _chg_text_color(chg: float) -> str:
        """根據漲跌幅深淺決定文字顏色"""
        return "#ffffff" if abs(chg) > 1.5 else "#1a1a2e"

    def _build_treemap_fig(labels, parents, values, colors, customs, title, height=580):
        fig = go.Figure(go.Treemap(
            labels=labels, parents=parents, values=values, customdata=customs,
            marker=dict(
                colors=colors, colorscale=CSCALE, cmid=0, cmin=-5, cmax=5,
                showscale=True,
                colorbar=dict(
                    title=dict(text="漲跌%", font=dict(size=11)),
                    thickness=12, len=0.65,
                    tickvals=[-5, -3, -1, 0, 1, 3, 5],
                    ticktext=["-5% 跌", "-3%", "-1%", "0", "+1%", "+3%", "+5% 漲"],
                    tickfont=dict(size=10),
                ),
                pad=dict(t=4, l=2, r=2, b=2),
                line=dict(width=1.5, color="#ffffff"),
            ),
            texttemplate=(
                "<b>%{label}</b>"
                "<br>%{customdata[0]}"
                "<br><b>%{customdata[1]}</b>"
            ),
            textposition="middle center",
            textfont=dict(size=13, family="Arial, sans-serif", color="#ffffff"),
            hovertemplate="<b>%{label}</b><br>現價：%{customdata[0]}<br>漲跌：%{customdata[1]}<extra></extra>",
            tiling=dict(packing="squarify", pad=3),
        ))
        fig.update_layout(
            margin=dict(t=50, l=5, r=80, b=5), height=height,
            paper_bgcolor="#0e1117", font=dict(color="#fafafa"),
            title=dict(text=f"<b>{title}</b>", font=dict(size=17, color="#fafafa"), x=0.01),
        )
        return fig

    def _make_hierarchical_treemap(nested_cfg: dict, title: str, tab_key: str):
        """兩層切換：第一層顯示分類，點選後切換為個股"""
        all_tickers = []
        for cat, stocks in nested_cfg.items():
            for name, ticker in stocks.items():
                all_tickers.append((f"{cat}|{name}", ticker))

        changes = fetch_nested_changes(tuple(all_tickers))

        cat_avgs = {}
        for cat, stocks in nested_cfg.items():
            cat_data = [changes[f"{cat}|{n}"] for n in stocks if f"{cat}|{n}" in changes]
            cat_chgs = [d[1] for d in cat_data]
            cat_avgs[cat] = round(sum(cat_chgs)/len(cat_chgs), 2) if cat_chgs else 0

        sorted_cats = sorted(nested_cfg.keys(), key=lambda c: cat_avgs.get(c, 0), reverse=True)

        sess_key = f"heatmap_cat_{tab_key}"
        if sess_key not in st.session_state:
            st.session_state[sess_key] = None

        selected_cat = st.session_state[sess_key]

        if selected_cat is None:
            # ── 第一層：分類熱力圖 + 下方按鈕列 ─────────────
            labels, parents, values, colors, customs = [], [], [], [], []
            for cat in sorted_cats:
                avg = cat_avgs[cat]
                sign = "▲" if avg > 0 else ("▼" if avg < 0 else "─")
                labels.append(cat)
                parents.append("")
                values.append(max(len(nested_cfg[cat]), 1))
                colors.append(avg)
                customs.append(["", f"{sign} {abs(avg):.2f}%"])

            fig = _build_treemap_fig(labels, parents, values, colors, customs,
                                     f"{title}　— 分類總覽")
            st.plotly_chart(fig, use_container_width=True, key=f"cat_{tab_key}")

            st.markdown("**點選分類查看個股：**")
            n_cols = min(len(sorted_cats), 6)
            btn_cols = st.columns(n_cols)
            for i, cat in enumerate(sorted_cats):
                avg = cat_avgs[cat]
                sign = "▲" if avg > 0 else ("▼" if avg < 0 else "─")
                if btn_cols[i % n_cols].button(f"{cat}  {sign}{abs(avg):.2f}%",
                                               key=f"btn_{tab_key}_{cat}",
                                               use_container_width=True):
                    st.session_state[sess_key] = cat
                    st.rerun()

        else:
            # ── 第二層：個股熱力圖 ────────────────────────────
            col_back, col_title = st.columns([1, 6])
            if col_back.button("← 返回", key=f"back_{tab_key}"):
                st.session_state[sess_key] = None
                st.rerun()
            col_title.markdown(f"### {selected_cat}")

            stocks = nested_cfg[selected_cat]
            sorted_stocks = sorted(
                stocks.keys(),
                key=lambda n: changes[f"{selected_cat}|{n}"][1] if f"{selected_cat}|{n}" in changes else 0,
                reverse=True,
            )
            labels, parents, values, colors, customs = [], [], [], [], []
            for name in sorted_stocks:
                key = f"{selected_cat}|{name}"
                if key in changes:
                    price, chg = changes[key]
                    sign = "▲" if chg > 0 else ("▼" if chg < 0 else "─")
                    clr, txt_p, txt_c = chg, f"{price:,.2f}", f"{sign} {abs(chg):.2f}%"
                else:
                    clr, txt_p, txt_c = 0, "—", "—"
                labels.append(name)
                parents.append("")
                values.append(1)
                colors.append(clr)
                customs.append([txt_p, txt_c])

            fig = _build_treemap_fig(labels, parents, values, colors, customs,
                                     f"{title}　— {selected_cat}", height=480)
            st.plotly_chart(fig, use_container_width=True, key=f"stock_{tab_key}")

    def _make_flat_treemap(changes: dict, title: str):
        if not changes:
            st.warning(f"{title} 資料暫時無法取得"); return
        items = sorted(changes.items(), key=lambda x: x[1], reverse=True)
        names = [i[0] for i in items]
        chgs  = [i[1] for i in items]
        signs = ["▲" if c > 0 else ("▼" if c < 0 else "") for c in chgs]
        labels_txt = [f"{n}<br><b>{s} {abs(c):.2f}%</b>" for n, c, s in zip(names, chgs, signs)]
        fig = go.Figure(go.Treemap(
            labels=labels_txt,
            parents=[""] * len(names),
            values=[1] * len(names),
            marker=dict(
                colors=chgs,
                colorscale=CSCALE, cmid=0, cmin=-5, cmax=5, showscale=False,
                pad=dict(t=3, l=2, r=2, b=2),
                line=dict(width=1.5, color="#ffffff"),
            ),
            textfont=dict(size=14, family="Arial, sans-serif", color="#ffffff"),
            hovertemplate="<b>%{label}</b><extra></extra>",
            tiling=dict(packing="squarify", pad=3),
        ))
        fig.update_layout(
            margin=dict(t=50, l=5, r=5, b=5),
            height=420,
            paper_bgcolor="#0e1117",
            font=dict(color="#fafafa"),
            title=dict(
                text=f"<b>{title}</b>",
                font=dict(size=17, color="#fafafa"),
                x=0.01,
            ),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── 熱力圖顯示 ────────────────────────────────────────
    group_keys = list(cfg.keys())
    if group_keys:
        tabs = st.tabs(group_keys)
        for tab, gkey in zip(tabs, group_keys):
            with tab:
                gval = cfg[gkey]
                with st.spinner(f"載入 {gkey} 資料..."):
                    if _is_nested(gval):
                        _make_hierarchical_treemap(gval, gkey, tab_key=gkey)
                    else:
                        _make_flat_treemap(fetch_sector_changes(gval), gkey)
    else:
        st.info("尚無群組設定，請在下方新增。")

    # ── 自訂板塊設定 ───────────────────────────────────────
    st.divider()
    with st.expander("⚙️ 自訂板塊設定", expanded=False):
        st.caption("格式支援兩種：\n- **巢狀**（推薦）：`[分類名]` 開頭，下面每行 `名稱, ticker`\n- **平面**：每行直接 `名稱, ticker`")

        _ge1, _ge2 = st.columns([3, 1])
        edit_mkt = _ge1.selectbox("選擇群組", group_keys, key="edit_mkt") if group_keys else None
        new_group_name = st.text_input("➕ 新增群組名稱", placeholder="例如：🔌 PCB細項", key="new_group")

        def _cfg_to_text(val):
            if _is_nested(val):
                lines = []
                for cat, stocks in val.items():
                    lines.append(f"[{cat}]")
                    for n, t in stocks.items():
                        lines.append(f"{n}, {t}")
                    lines.append("")
                return "\n".join(lines).strip()
            else:
                return "\n".join(f"{k}, {v}" for k, v in val.items())

        def _text_to_cfg(text):
            result = {}
            cur_cat = None
            for line in text.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("[") and line.endswith("]"):
                    cur_cat = line[1:-1].strip()
                    result.setdefault(cur_cat, {})
                else:
                    parts = [p.strip() for p in line.split(",", 1)]
                    if len(parts) == 2 and parts[0] and parts[1]:
                        if cur_cat:
                            result[cur_cat][parts[0]] = parts[1]
                        else:
                            result[parts[0]] = parts[1]
            return result

        current_text = _cfg_to_text(cfg[edit_mkt]) if edit_mkt else ""
        new_text = st.text_area("板塊清單", value=current_text, height=340, key="sector_text",
            placeholder="[IC設計]\n聯發科, 2454.TW\n瑞昱, 2379.TW\n\n[石英]\n台灣石英, 4912.TW")

        col_save, col_reset, col_del = st.columns([1.2, 1, 1])
        with col_save:
            if st.button("💾 儲存", type="primary"):
                target = new_group_name.strip() if new_group_name.strip() else edit_mkt
                if not target:
                    st.warning("請選擇或輸入群組名稱")
                else:
                    parsed = _text_to_cfg(new_text)
                    if not parsed:
                        st.error("格式錯誤，請確認內容")
                    else:
                        cfg[target] = parsed
                        with open(SECTOR_CFG, "w", encoding="utf-8") as f:
                            json.dump(cfg, f, ensure_ascii=False, indent=2)
                        fetch_sector_changes.clear()
                        st.success(f"已儲存「{target}」")
                        st.rerun()
        with col_reset:
            if st.button("↩️ 恢復全部預設"):
                with open(SECTOR_CFG, "w", encoding="utf-8") as f:
                    json.dump(DEFAULT_CFG, f, ensure_ascii=False, indent=2)
                fetch_sector_changes.clear()
                st.rerun()
        with col_del:
            if edit_mkt and st.button("🗑️ 刪除此群組", type="secondary"):
                cfg.pop(edit_mkt, None)
                with open(SECTOR_CFG, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                fetch_sector_changes.clear()
                st.rerun()
# ==================== 個股研究 ====================
elif page == "🔬 個股研究":
    st.title("🔬 個股研究")

    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    RESEARCH_DIR = os.path.join(DATA_DIR, "research")
    os.makedirs(RESEARCH_DIR, exist_ok=True)
    RESEARCH_INDEX = os.path.join(RESEARCH_DIR, "index.json")

    # 讀取研究索引
    if os.path.exists(RESEARCH_INDEX):
        with open(RESEARCH_INDEX, "r", encoding="utf-8") as f:
            research_db = json.load(f)
    else:
        research_db = {}  # {ticker: [{id, title, date, tags, content, files:[{name,path}]}]}

    # _cats / _names: {ticker: ...} 儲存在同一個 json 的特殊 key
    _cats: dict  = research_db.pop("__cats__", {})
    _names: dict = research_db.pop("__names__", {})

    def _save_index():
        save_data = dict(research_db)
        save_data["__cats__"]  = _cats
        save_data["__names__"] = _names
        with open(RESEARCH_INDEX, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

    @st.cache_data(ttl=60 * 60 * 24)
    def _fetch_stock_name(ticker: str) -> str:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
        h = {"User-Agent": "Mozilla/5.0"}
        try:
            r = requests.get(url, headers=h, verify=False, timeout=8)
            meta = r.json()["chart"]["result"][0]["meta"]
            return meta.get("shortName") or meta.get("longName") or ""
        except Exception:
            return ""

    def _resolve_ticker(raw: str) -> tuple:
        """輸入代號自動偵測市場並回傳 (ticker, name)"""
        raw = raw.strip()
        if not raw:
            return "", ""
        if raw.upper().endswith((".TW", ".TWO", ".T", ".KS", ".KQ")):
            candidates = [raw.upper()]
        elif raw.isdigit():
            if len(raw) == 6:                          # 韓股 6位數
                candidates = [raw + ".KS", raw + ".KQ"]
            elif len(raw) == 5:                        # 日股 5位數
                candidates = [raw + ".T"]
            else:                                      # 台股 4位數
                candidates = [raw + ".TW", raw + ".TWO", raw + ".T"]
        else:
            candidates = [raw.upper()]                 # 美股英文代號
        for t in candidates:
            name = _fetch_stock_name(t)
            if name:
                return t, name
        return candidates[0], ""

    import uuid

    # ── 左右欄：股票選擇 + 新增 ────────────────────────
    left_r, right_r = st.columns([1, 2.2])

    with left_r:
        st.subheader("📂 股票清單")

        # 新增股票 + 分類
        with st.expander("➕ 新增股票", expanded=False):
            _new_raw = st.text_input("股票代號", placeholder="2330 / AAPL / 8035 / 005930",
                                     key="research_new_ticker")
            _resolved_ticker, _resolved_name = "", ""
            if _new_raw.strip():
                with st.spinner("查詢中…"):
                    _resolved_ticker, _resolved_name = _resolve_ticker(_new_raw)
                if _resolved_name:
                    st.success(f"✅ {_resolved_ticker}　{_resolved_name}")
                else:
                    st.warning(f"找不到名稱，將以 {_resolved_ticker} 儲存")

            all_cats_set = sorted(set(_cats.values())) if _cats else []
            _cat_sel     = st.selectbox("分類", all_cats_set + ["（新分類）"],
                                        key="research_cat_sel") if all_cats_set else "（新分類）"
            _new_cat_inp = st.text_input("新分類名稱", placeholder="例如：晶圓代工",
                                         key="research_new_cat") if (not all_cats_set or _cat_sel == "（新分類）") else ""
            if st.button("➕ 新增", key="add_research_ticker", type="primary"):
                t   = _resolved_ticker or _new_raw.strip()
                cat = (_new_cat_inp.strip() if _cat_sel == "（新分類）" else _cat_sel) or "未分類"
                if t and t not in research_db:
                    research_db[t] = []
                    _cats[t]  = cat
                    _names[t] = _resolved_name
                    _save_index()
                    st.rerun()
                elif t in research_db:
                    st.warning("已存在")

        st.divider()

        # 依分類分組顯示
        all_tickers = [k for k in research_db.keys() if k != "__cats__"]
        grouped: dict[str, list] = {}
        for tk in sorted(all_tickers):
            c = _cats.get(tk, "未分類")
            grouped.setdefault(c, []).append(tk)

        sel_ticker = None
        if grouped:
            for cat_name, tickers in sorted(grouped.items()):
                with st.expander(f"📁 {cat_name}（{len(tickers)}）", expanded=True):
                    for tk in tickers:
                        note_count = len(research_db.get(tk, []))
                        nm = _names.get(tk, "")
                        label = f"{tk}  {nm}  ({note_count})" if nm else (f"{tk}  ({note_count})" if note_count else tk)
                        if st.button(label, key=f"sel_{tk}", use_container_width=True):
                            st.session_state["research_sel"] = tk
            sel_ticker = st.session_state.get("research_sel")
            # 確認仍存在
            if sel_ticker and sel_ticker not in research_db:
                sel_ticker = None
        else:
            st.info("點擊上方「新增股票」開始使用")

    with right_r:
        if sel_ticker:
            _r_title_col, _r_cat_col = st.columns([2, 1.5])
            _sn = _names.get(sel_ticker, "")
            _r_title_col.subheader(f"📝 {sel_ticker}　{_sn}" if _sn else f"📝 {sel_ticker} 研究筆記")
            with _r_cat_col:
                _cur_cat    = _cats.get(sel_ticker, "未分類")
                _all_c      = sorted(set(list(_cats.values()) + ["未分類"]))
                _edit_cat   = st.selectbox("分類", _all_c + ["＋ 新分類"],
                                           index=_all_c.index(_cur_cat) if _cur_cat in _all_c else 0,
                                           key=f"edit_cat_{sel_ticker}")
                if _edit_cat == "＋ 新分類":
                    _edit_cat = st.text_input("輸入新分類", key=f"new_cat_{sel_ticker}")
                if _edit_cat and _edit_cat != _cur_cat:
                    _cats[sel_ticker] = _edit_cat
                    _save_index()
                    st.rerun()

            ticker_dir = os.path.join(RESEARCH_DIR, sel_ticker)
            os.makedirs(ticker_dir, exist_ok=True)

            # ── 新增筆記表單 ──────────────────────────────
            with st.expander("➕ 新增筆記 / 報告", expanded=len(research_db.get(sel_ticker, [])) == 0):
                n_title = st.text_input("標題", placeholder="例如：2025Q1 法人報告摘要", key="n_title")
                _nc1, _nc2, _nc3 = st.columns([1.5, 1, 1])
                n_date   = _nc1.date_input("日期", value=datetime.date.today(), key="n_date")
                n_target = _nc2.number_input("目標價格", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="n_target")
                n_tags   = _nc3.text_input("標籤（逗號分隔）", placeholder="法人, 技術面", key="n_tags")
                n_content = st.text_area("筆記內容", height=180, key="n_content",
                    placeholder="在此填寫研究內容、摘要、觀點…")
                n_files = st.file_uploader("上傳附件（PDF、圖片、Excel…）",
                    accept_multiple_files=True, key="n_files",
                    type=["pdf","png","jpg","jpeg","xlsx","xls","csv","docx","txt","pptx"])

                if st.button("💾 儲存筆記", type="primary", key="save_note"):
                    if not n_title.strip():
                        st.warning("請填寫標題")
                    else:
                        note_id = str(uuid.uuid4())[:8]
                        saved_files = []
                        for uf in (n_files or []):
                            save_path = os.path.join(ticker_dir, f"{note_id}_{uf.name}")
                            with open(save_path, "wb") as fp:
                                fp.write(uf.read())
                            saved_files.append({"name": uf.name, "path": save_path})

                        research_db.setdefault(sel_ticker, []).insert(0, {
                            "id": note_id,
                            "title": n_title.strip(),
                            "date": str(n_date),
                            "target_price": n_target if n_target > 0 else None,
                            "tags": [t.strip() for t in n_tags.split(",") if t.strip()],
                            "content": n_content.strip(),
                            "files": saved_files,
                        })
                        _save_index()
                        st.success("已儲存")
                        st.rerun()

            st.divider()

            # ── 筆記列表 ─────────────────────────────────
            notes = research_db.get(sel_ticker, [])
            if not notes:
                st.info("尚無筆記，請於上方新增")
            else:
                _tag_filter = st.text_input("🔍 依標籤篩選", placeholder="例如：法人報告", key="tag_filter")
                if _tag_filter.strip():
                    notes = [n for n in notes if any(_tag_filter.strip().lower() in t.lower() for t in n.get("tags", []))]

                for note in notes:
                    nid = note["id"]
                    tags_html = " ".join(
                        f'<span style="background:#4a7fa5;color:#fff;font-size:11px;padding:2px 7px;border-radius:10px;font-family:monospace">{t}</span>'
                        for t in note.get("tags", [])
                    )
                    _tp = note.get("target_price")
                    _tp_html = f'<span style="background:#ff8f00;color:#fff;font-size:11px;padding:2px 8px;border-radius:10px;font-weight:700;margin-left:8px">🎯 目標價 {_tp}</span>' if _tp else ""
                    st.markdown(f"""
<div style="background:#f0f6ff;border-left:4px solid #4a7fa5;border-radius:6px;padding:12px 16px;margin-bottom:4px">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div style="font-weight:700;font-size:15px">{note['title']}{_tp_html}</div>
    <div style="font-family:monospace;font-size:12px;color:#5B6573">{note['date']}</div>
  </div>
  <div style="margin-top:6px">{tags_html}</div>
</div>""", unsafe_allow_html=True)

                    with st.expander("展開內容與附件", expanded=False):
                        if note.get("content"):
                            st.markdown(note["content"])

                        if note.get("files"):
                            st.markdown("**📎 附件**")
                            for finfo in note["files"]:
                                fpath = finfo["path"]
                                fname = finfo["name"]
                                if os.path.exists(fpath):
                                    with open(fpath, "rb") as fp:
                                        st.download_button(
                                            label=f"⬇️ {fname}",
                                            data=fp.read(),
                                            file_name=fname,
                                            key=f"dl_{nid}_{fname}",
                                        )
                                else:
                                    st.caption(f"⚠️ 找不到檔案：{fname}")

                        # 刪除此筆記
                        if st.button("🗑️ 刪除此筆記", key=f"del_note_{nid}"):
                            for finfo in note.get("files", []):
                                try:
                                    os.remove(finfo["path"])
                                except Exception:
                                    pass
                            research_db[sel_ticker] = [n for n in research_db[sel_ticker] if n["id"] != nid]
                            _save_index()
                            st.rerun()

            # 刪除整個股票
            st.divider()
            if st.button(f"🗑️ 刪除 {sel_ticker} 所有研究", type="secondary", key="del_ticker"):
                import shutil
                research_db.pop(sel_ticker, None)
                _save_index()
                try:
                    shutil.rmtree(ticker_dir)
                except Exception:
                    pass
                st.rerun()
