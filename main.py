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
page = st.sidebar.radio("選擇頁面", ["🏠 選股系統", "🌍 總經儀表板", "📰 新聞監控", "📊 散戶指標", "📈 個股監控", "🌡️ 板塊熱力圖", "🔬 個股研究", "🎙️ Podcast 整理"])

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

    # TAIFEX commodity_id → FinMind data_id 對照
    _FINMIND_ID_MAP = {"MXF": "MTX", "TMF": "TMF", "TXF": "TX"}

    def _today_cache_key():
        """17:00 後才算「今天已更新」，否則用昨天的快取"""
        import pytz
        now = datetime.datetime.now(pytz.timezone("Asia/Taipei"))
        if now.hour < 17:
            return (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        return now.strftime("%Y-%m-%d")

    @st.cache_data(ttl=60 * 60 * 24)
    def _fetch_institutional_trend(commodity_id, n_days, _cache_date):
        """改用 FinMind API，可跨國存取（TAIFEX 封鎖海外 IP）
        _cache_date 當作 cache key，同一天只抓一次，17:00 後才取當日資料"""
        fm_id = _FINMIND_ID_MAP.get(commodity_id, commodity_id)
        start = (datetime.date.today() - datetime.timedelta(days=n_days * 2)).strftime("%Y-%m-%d")
        try:
            token = st.secrets.get("FINMIND_TOKEN", "")
            r = requests.get(
                "https://api.finmindtrade.com/api/v4/data",
                params={"dataset": "TaiwanFuturesInstitutionalInvestors",
                        "data_id": fm_id, "start_date": start, "token": token},
                timeout=20)
            raw = r.json().get("data", [])
            if not raw:
                return pd.DataFrame()
            df = pd.DataFrame(raw)
            df["date"] = pd.to_datetime(df["date"])

            rows = []
            for date, grp in df.groupby("date"):
                def get_net(name):
                    row = grp[grp["institutional_investors"] == name]
                    if row.empty:
                        return 0.0
                    return float(row["long_open_interest_balance_volume"].iloc[0]) - \
                           float(row["short_open_interest_balance_volume"].iloc[0])
                dealer  = get_net("自營商")
                ita     = get_net("投信")
                foreign = get_net("外資")
                inst_sum = dealer + ita + foreign
                rows.append({
                    "日期": date, "自營商淨OI": dealer, "投信淨OI": ita, "外資淨OI": foreign,
                    "三大法人合計淨OI": inst_sum,
                })
            result = pd.DataFrame(rows).sort_values("日期").tail(n_days).reset_index(drop=True)
            return result
        except Exception:
            return pd.DataFrame()

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
            df_r = _fetch_institutional_trend(commodity_id, n_days=20, _cache_date=_today_cache_key())
            if "三大法人合計淨OI" not in df_r.columns or df_r.empty:
                st.warning(f"目前無法取得{label}三大法人資料，請稍後再試。")
                return
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
        df_inst = _fetch_institutional_trend("TXF", n_days=20, _cache_date=_today_cache_key())
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

# ==================== 個股監控 ====================
elif page == "📈 個股監控":
    st.title("📈 個股監控")
    st_autorefresh(interval=5 * 60 * 1000, key="holdings_refresh")

    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(DATA_DIR, exist_ok=True)
    SECTOR_CFG_FILE = os.path.join(DATA_DIR, "sector_config.json")

    # ── 讀取板塊設定（與熱力圖共用）──────────────────
    _SEC_DEFAULT = {
        "🇹🇼 台股": {
            "晶圓代工": {"台積電":"2330.TW","聯電":"2303.TW"},
            "IC設計":   {"聯發科":"2454.TW","瑞昱":"2379.TW","聯詠":"3034.TW"},
            "封測":     {"日月光":"3711.TW"},
            "DRAM":     {"南亞科":"2408.TW","華邦電":"2344.TW"},
            "伺服器/EMS":{"廣達":"2382.TW","緯穎":"6669.TW","緯創":"3231.TW","鴻海":"2317.TW"},
            "金融":     {"富邦金":"2881.TW","國泰金":"2882.TW","中信金":"2891.TW"},
        },
    }
    if os.path.exists(SECTOR_CFG_FILE):
        with open(SECTOR_CFG_FILE, "r", encoding="utf-8") as f:
            _sec_cfg = json.load(f)
    else:
        _sec_cfg = _SEC_DEFAULT

    def _is_nested_cfg(gval):
        return any(isinstance(v, dict) for v in gval.values())

    @st.cache_data(ttl=60 * 10)
    def _fetch_price_chg(ticker: str):
        """回傳 (price, chg%) 或 None"""
        h = {"User-Agent": "Mozilla/5.0"}
        candidates = []
        if ticker.endswith(".TW"):
            candidates = [ticker, ticker[:-3] + ".TWO"]
        elif ticker.endswith(".TWO"):
            candidates = [ticker, ticker[:-4] + ".TW"]
        elif ticker.endswith(".T"):
            candidates = [ticker]
        else:
            candidates = [ticker]
        for t in candidates:
            try:
                r = requests.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?interval=1d&range=5d",
                    headers=h, verify=False, timeout=8)
                closes = [c for c in r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
                if len(closes) >= 2:
                    chg = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)
                    return round(closes[-1], 2), chg
            except Exception:
                continue
        return None

    @st.cache_data(ttl=60 * 15)
    def _fetch_kline_ticker(ticker: str, interval: str, range_: str):
        """支援完整 ticker（含後綴）的 K 線"""
        h = {"User-Agent": "Mozilla/5.0"}
        candidates = []
        if ticker.endswith(".TW"):
            candidates = [ticker, ticker[:-3] + ".TWO"]
        elif ticker.endswith(".TWO"):
            candidates = [ticker, ticker[:-4] + ".TW"]
        else:
            candidates = [ticker]
        for t in candidates:
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?interval={interval}&range={range_}"
                res = requests.get(url, headers=h, verify=False, timeout=15)
                result = res.json()["chart"]["result"][0]
                timestamps = result["timestamp"]
                q = result["indicators"]["quote"][0]
                df = pd.DataFrame({
                    "date": pd.to_datetime([datetime.datetime.fromtimestamp(ts) for ts in timestamps]),
                    "open": q["open"], "high": q["high"],
                    "low": q["low"],   "close": q["close"],
                    "volume": q.get("volume", [None]*len(timestamps)),
                })
                df = df.dropna(subset=["open","high","low","close"])
                if not df.empty:
                    return df.sort_values("date").reset_index(drop=True)
            except Exception:
                continue
        return pd.DataFrame()

    def _save_sec_cfg(cfg):
        with open(SECTOR_CFG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

    def _resolve_ticker_ig(raw: str):
        """回傳 (ticker, name)，支援中文名稱、英文代號、數字代號"""
        raw = raw.strip()
        h = {"User-Agent": "Mozilla/5.0"}

        # ── 中文輸入：先搜 sector_config，再用 Yahoo 搜尋 API ──
        has_cjk = any('一' <= c <= '鿿' for c in raw)
        if has_cjk:
            # 1. 在現有設定中比對名稱
            for grp in _sec_cfg.values():
                for cat_val in grp.values():
                    if isinstance(cat_val, dict):
                        for n, t in cat_val.items():
                            if raw in n or n in raw:
                                return t, n
            # 2. Yahoo Finance search API
            try:
                r = requests.get(
                    f"https://query1.finance.yahoo.com/v1/finance/search?q={requests.utils.quote(raw)}&lang=zh-TW&region=TW&quotesCount=5",
                    headers=h, verify=False, timeout=8)
                quotes = r.json().get("quotes", [])
                for q in quotes:
                    sym = q.get("symbol", "")
                    if sym and (sym.endswith(".TW") or sym.endswith(".TWO")):
                        return sym, q.get("shortname") or q.get("longname") or raw
                # fallback: 第一個結果
                if quotes:
                    q = quotes[0]
                    sym = q.get("symbol", raw.upper())
                    return sym, q.get("shortname") or q.get("longname") or raw
            except Exception:
                pass
            return raw, raw

        # ── 英數代號 ──
        if raw.upper().endswith((".TW", ".TWO", ".T", ".KS", ".KQ")):
            candidates = [raw.upper()]
        elif raw.isdigit():
            if len(raw) == 6:
                candidates = [raw + ".KS", raw + ".KQ"]
            elif len(raw) == 5:
                candidates = [raw + ".T"]
            else:
                candidates = [raw + ".TW", raw + ".TWO"]
        else:
            candidates = [raw.upper()]

        # 先在現有設定找已知中文名稱
        for t in candidates:
            for grp in _sec_cfg.values():
                for cat_val in grp.values():
                    if isinstance(cat_val, dict):
                        for n, tk in cat_val.items():
                            if tk == t:
                                return t, n

        # 台股：用 TWSE/TPEX API 取中文名稱
        for t in candidates:
            code = t.split(".")[0]
            if t.endswith(".TW"):
                try:
                    r = requests.get(
                        f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{code}.tw&json=1&delay=0",
                        headers=h, verify=False, timeout=8)
                    arr = r.json().get("msgArray", [])
                    if arr and arr[0].get("n"):
                        return t, arr[0]["n"]
                except Exception:
                    pass
            elif t.endswith(".TWO"):
                try:
                    r = requests.get(
                        f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=otc_{code}.tw&json=1&delay=0",
                        headers=h, verify=False, timeout=8)
                    arr = r.json().get("msgArray", [])
                    if arr and arr[0].get("n"):
                        return t, arr[0]["n"]
                except Exception:
                    pass

        # fallback：Yahoo Finance meta（日股/美股保留英文名）
        for t in candidates:
            try:
                r = requests.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?interval=1d&range=5d",
                    headers=h, verify=False, timeout=8)
                meta = r.json()["chart"]["result"][0]["meta"]
                name = meta.get("shortName") or meta.get("longName") or ""
                if name:
                    return t, name
            except Exception:
                continue
        return candidates[0], ""

    if "ig_btn_idx" not in st.session_state:
        st.session_state["ig_btn_idx"] = 0
    st.session_state["ig_btn_idx"] = 0  # reset each render pass

    def _render_stock_btn(name, ticker, group_key):
        st.session_state["ig_btn_idx"] += 1
        _idx = st.session_state["ig_btn_idx"]
        pc = _fetch_price_chg(ticker)
        if pc:
            price, chg = pc
            sign  = "▲" if chg > 0 else ("▼" if chg < 0 else "－")
            color = "#ef5350" if chg > 0 else ("#26a69a" if chg < 0 else "#888")
            sub   = f'<span style="font-size:11px;color:{color}">{sign}{abs(chg):.2f}%　{price:,.2f}</span>'
        else:
            sub = '<span style="font-size:11px;color:#aaa">—</span>'
        sel_key = f"{group_key}|{ticker}"
        is_sel  = st.session_state.get("ig_sel") == sel_key
        btn_col, del_col = st.columns([5, 1])
        with btn_col:
            if st.button(("▶ " if is_sel else "") + name,
                         key=f"ig_{ticker}_{_idx}", use_container_width=True,
                         type="primary" if is_sel else "secondary"):
                st.session_state["ig_sel"] = sel_key
                st.session_state["ig_ticker"] = ticker
                st.session_state["ig_name"]   = name
                st.rerun()
            st.markdown(sub, unsafe_allow_html=True)
        with del_col:
            if st.button("✕", key=f"igdel_{ticker}_{_idx}", help="從清單移除"):
                # 從 sector_config 中刪除此 ticker
                for grp in _sec_cfg:
                    for cat in list(_sec_cfg[grp].keys()):
                        cat_val = _sec_cfg[grp][cat]
                        if isinstance(cat_val, dict):
                            to_del = [n for n, t in cat_val.items() if t == ticker]
                            for n in to_del:
                                del _sec_cfg[grp][cat][n]
                            if not _sec_cfg[grp][cat]:
                                del _sec_cfg[grp][cat]
                        elif cat_val == ticker:
                            del _sec_cfg[grp][cat]
                _save_sec_cfg(_sec_cfg)
                if st.session_state.get("ig_ticker") == ticker:
                    st.session_state.pop("ig_ticker", None)
                    st.session_state.pop("ig_sel", None)
                st.rerun()

    left_col, right_col = st.columns([1, 1.8])

    with left_col:
        tab_add, tab_browse = st.tabs(["➕ 新增個股", "📂 板塊瀏覽"])

        # ── 新增個股 tab ────────────────────────────────
        with tab_add:
            with st.form("ig_add_form", clear_on_submit=True):
                raw_ticker = st.text_input("股票代號", placeholder="例：2330 / AAPL / 8035.T")
                group_options = list(_sec_cfg.keys())
                sel_group_add = st.selectbox("市場群組", group_options, key="ig_add_group")
                existing_cats = list(_sec_cfg.get(sel_group_add, {}).keys()) if sel_group_add else []
                cat_options   = existing_cats + ["＋ 新增分類"]
                sel_cat       = st.selectbox("分類", cat_options, key="ig_add_cat")
                new_cat_name  = ""
                if sel_cat == "＋ 新增分類":
                    new_cat_name = st.text_input("新分類名稱")
                submitted = st.form_submit_button("新增")

            if submitted:
                raw_ticker = raw_ticker.strip()
                if not raw_ticker:
                    st.warning("請輸入股票代號")
                else:
                    resolved_ticker, resolved_name = _resolve_ticker_ig(raw_ticker)
                    if not resolved_name:
                        resolved_name = raw_ticker.upper()
                    target_cat = new_cat_name.strip() if sel_cat == "＋ 新增分類" else sel_cat
                    if not target_cat:
                        st.warning("請輸入分類名稱")
                    else:
                        if sel_group_add not in _sec_cfg:
                            _sec_cfg[sel_group_add] = {}
                        if target_cat not in _sec_cfg[sel_group_add]:
                            _sec_cfg[sel_group_add][target_cat] = {}
                        cat_obj = _sec_cfg[sel_group_add][target_cat]
                        if isinstance(cat_obj, dict):
                            cat_obj[resolved_name] = resolved_ticker
                        else:
                            _sec_cfg[sel_group_add][target_cat] = {resolved_name: resolved_ticker}
                        _save_sec_cfg(_sec_cfg)
                        st.success(f"已新增：{resolved_name}（{resolved_ticker}）→ {sel_group_add} / {target_cat}")
                        st.rerun()

        # ── 板塊瀏覽 tab ────────────────────────────────
        with tab_browse:
            group_keys = list(_sec_cfg.keys())
            _sel_group = st.radio("市場", group_keys, horizontal=True, key="ig_group") if group_keys else None

            if _sel_group:
                gval = _sec_cfg[_sel_group]
                if _is_nested_cfg(gval):
                    for cat, stocks in gval.items():
                        with st.expander(f"**{cat}**（{len(stocks)}）", expanded=False):
                            for name, ticker in stocks.items():
                                _render_stock_btn(name, ticker, _sel_group)
                else:
                    for name, ticker in gval.items():
                        _render_stock_btn(name, ticker, _sel_group)

    with right_col:
        sel_ticker = st.session_state.get("ig_ticker")
        sel_name   = st.session_state.get("ig_name", "")
        if not sel_ticker:
            st.info("← 左側點選股票查看 K 線")
        else:
            st.subheader(f"📈 {sel_name}　`{sel_ticker}`")
            KLINE_SCALES = {"1小時": ("60m","1mo"), "日": ("1d","6mo"), "週": ("1wk","2y"), "月": ("1mo","5y")}
            kline_scale = st.selectbox("K棒尺度", list(KLINE_SCALES.keys()), index=1, key="ig_kscale")
            kline_interval, kline_range = KLINE_SCALES[kline_scale]
            df_k = _fetch_kline_ticker(sel_ticker, kline_interval, kline_range)
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
                    if all(v == v for v in [o, h, l, c])
                ]
                volume_data = []
                if "volume" in df_k.columns:
                    volume_data = [
                        {"time": t, "value": float(v) if v == v else 0,
                         "color": "#ef535088" if float(c) >= float(o) else "#26a69a88"}
                        for t, v, o, c in zip(times, df_k["volume"], df_k["open"], df_k["close"])
                        if v == v
                    ]

                # ── 型態訊號偵測 ──────────────────────────────
                def _local_sr(df_slice, current_price):
                    """從 df_slice（不含當前 K 棒）找最近支撐與壓力"""
                    if len(df_slice) < 6:
                        return [], []
                    window = 3
                    highs_s = df_slice["high"].tolist()
                    lows_s  = df_slice["low"].tolist()
                    sups, ress = [], []
                    for j in range(window, len(df_slice) - window):
                        h_before = max(highs_s[j-window:j])
                        h_after  = max(highs_s[j+1:j+window+1])
                        l_before = min(lows_s[j-window:j])
                        l_after  = min(lows_s[j+1:j+window+1])
                        if highs_s[j] > h_before and highs_s[j] > h_after and highs_s[j] > current_price:
                            ress.append(highs_s[j])
                        if lows_s[j] < l_before and lows_s[j] < l_after and lows_s[j] < current_price:
                            sups.append(lows_s[j])
                    # 各取離現價最近一條
                    nearest_sup = [min(sups, key=lambda x: current_price - x)] if sups else []
                    nearest_res = [min(ress, key=lambda x: x - current_price)] if ress else []
                    return nearest_sup, nearest_res

                def _detect_signals(df):
                    """支撐壓力由前面 K 棒確立；破底翻/假突破允許後續 1~3 根確認"""
                    sigs = []
                    if len(df) < 10:
                        return sigs
                    closes = df["close"].tolist()
                    lows   = df["low"].tolist()
                    _times = times
                    lookback    = 40   # 往前幾根建立支撐壓力
                    confirm_win = 3    # 破底/突破後幾根內確認翻轉

                    # 避免同一事件重複標記
                    marked = set()

                    for i in range(10, len(df) - confirm_win):
                        start = max(0, i - lookback)
                        # 支撐壓力只看 i 之前的 K 棒
                        df_before = df.iloc[start:i]
                        c_cur = closes[i]
                        sup_list, res_list = _local_sr(df_before, c_cur)

                        for sup in sup_list:
                            tol = sup * 0.012
                            c_prev = closes[i-1]

                            # ── 破底：前一根在支撐上，當根收盤明確跌破 ──
                            if c_prev > sup and c_cur < sup - tol and ("破底", i) not in marked:
                                sigs.append({"time": _times[i], "position": "belowBar",
                                             "shape": "arrowDown", "color": "#ef5350",
                                             "text": "破底"})
                                marked.add(("破底", i))

                                # ── 破底翻：跌破後 1~3 根內站回支撐上 ──
                                for k in range(i + 1, min(i + confirm_win + 1, len(df))):
                                    if closes[k] > sup and ("破底翻", k) not in marked:
                                        sigs.append({"time": _times[k], "position": "belowBar",
                                                     "shape": "arrowUp", "color": "#ff9800",
                                                     "text": "破底翻"})
                                        marked.add(("破底翻", k))
                                        break

                        for res in res_list:
                            tol = res * 0.012
                            c_prev = closes[i-1]

                            # ── 突破：前一根在壓力下，當根收盤明確突破 ──
                            if c_prev < res and c_cur > res + tol and ("突破", i) not in marked:
                                sigs.append({"time": _times[i], "position": "aboveBar",
                                             "shape": "arrowUp", "color": "#26a69a",
                                             "text": "突破"})
                                marked.add(("突破", i))

                                # ── 假突破：突破後 1~3 根內跌回壓力下 ──
                                for k in range(i + 1, min(i + confirm_win + 1, len(df))):
                                    if closes[k] < res and ("假突破", k) not in marked:
                                        sigs.append({"time": _times[k], "position": "aboveBar",
                                                     "shape": "arrowDown", "color": "#ab47bc",
                                                     "text": "假突破"})
                                        marked.add(("假突破", k))
                                        break
                    return sigs

                signals = _detect_signals(df_k)

                chart_options = {
                    "layout": {"background": {"type": "solid", "color": "#131722"},
                               "textColor": "#d1d4dc"},
                    "grid": {"vertLines": {"color": "#1e2130"}, "horzLines": {"color": "#1e2130"}},
                    "crosshair": {"mode": 0},
                    "rightPriceScale": {"borderColor": "#2a2e39"},
                    "timeScale": {"borderColor": "#2a2e39", "timeVisible": kline_interval == "60m"},
                }

                # 蠟燭圖（含訊號標記）
                candle_series = {
                    "type": "Candlestick",
                    "data": candle_data,
                    "options": {"upColor":"#ef5350","downColor":"#26a69a",
                                "borderUpColor":"#ef5350","borderDownColor":"#26a69a",
                                "wickUpColor":"#ef5350","wickDownColor":"#26a69a"},
                }
                if signals:
                    candle_series["markers"] = signals

                series_list = [candle_series]

                # 成交量
                if volume_data:
                    series_list.append({"type": "Histogram", "data": volume_data,
                                        "options": {"priceFormat": {"type": "volume"}, "priceScaleId": "vol"},
                                        "priceScale": {"scaleMargins": {"top": 0.82, "bottom": 0}}})

                # 支撐壓力線
                sr_levels = compute_support_resistance(df_k)
                for level_price, label, ltype in sr_levels:
                    color = "#26a69a" if ltype == "support" else "#ef5350"
                    series_list.append({
                        "type": "Line",
                        "data": [{"time": times[0], "value": round(float(level_price), 4)},
                                 {"time": times[-1], "value": round(float(level_price), 4)}],
                        "options": {"color": color, "lineWidth": 1, "lineStyle": 2,
                                    "title": f"{'支撐' if ltype=='support' else '壓力'} {level_price:.2f}"},
                    })

                # MA 均線
                if len(df_k) >= 5:
                    ma5 = df_k["close"].rolling(5).mean()
                    series_list.append({"type": "Line",
                        "data": [{"time": t, "value": round(float(v), 4)} for t, v in zip(times, ma5) if pd.notna(v)],
                        "options": {"color": "#ff9800", "lineWidth": 1, "title": "MA5"}})
                if len(df_k) >= 20:
                    ma20 = df_k["close"].rolling(20).mean()
                    series_list.append({"type": "Line",
                        "data": [{"time": t, "value": round(float(v), 4)} for t, v in zip(times, ma20) if pd.notna(v)],
                        "options": {"color": "#2196f3", "lineWidth": 1, "title": "MA20"}})

                # 訊號圖例
                if signals:
                    sig_counts = {}
                    for s in signals:
                        sig_counts[s["text"]] = sig_counts.get(s["text"], 0) + 1
                    colors_map = {"突破":"#26a69a","假突破":"#ab47bc","破底翻":"#ff9800","破底":"#ef5350"}
                    legend_parts = []
                    for k, v in sig_counts.items():
                        clr = colors_map.get(k, "#fff")
                        legend_parts.append(f"<span style='color:{clr};margin-right:12px'>●&nbsp;{k}({v})</span>")
                    st.markdown("**型態訊號：** " + "".join(legend_parts), unsafe_allow_html=True)

                st.caption(f"{sel_name} {sel_ticker} K線圖（{kline_scale}）")
                renderLightweightCharts([{"chart": chart_options, "series": series_list}], key=f"ig_kline_{sel_ticker}_{kline_scale}")

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

    @st.cache_data(ttl=60 * 10)
    def _fetch_current_price(ticker: str) -> float | None:
        h = {"User-Agent": "Mozilla/5.0"}
        candidates = []
        if ticker.endswith(".TW"):
            candidates = [ticker, ticker[:-3] + ".TWO"]
        elif ticker.endswith(".TWO"):
            candidates = [ticker, ticker[:-4] + ".TW"]
        else:
            candidates = [ticker]
        for t in candidates:
            try:
                r = requests.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?interval=1d&range=5d",
                    headers=h, verify=False, timeout=8)
                closes = [c for c in r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
                if closes:
                    return round(closes[-1], 2)
            except Exception:
                continue
        return None

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
                    _tp_html = ""
                    if _tp:
                        _cur_p = _fetch_current_price(sel_ticker)
                        if _cur_p and _cur_p > 0:
                            _upside = (_tp - _cur_p) / _cur_p * 100
                            _up_color = "#e53935" if _upside >= 0 else "#26a69a"
                            _up_sign  = "▲" if _upside >= 0 else "▼"
                            _tp_html = (
                                f'<span style="background:#ff8f00;color:#fff;font-size:11px;padding:2px 8px;border-radius:10px;font-weight:700;margin-left:8px">🎯 目標價 {_tp}</span>'
                                f'<span style="background:{_up_color};color:#fff;font-size:11px;padding:2px 8px;border-radius:10px;font-weight:700;margin-left:4px">{_up_sign} 潛在漲幅 {abs(_upside):.1f}%</span>'
                            )
                        else:
                            _tp_html = f'<span style="background:#ff8f00;color:#fff;font-size:11px;padding:2px 8px;border-radius:10px;font-weight:700;margin-left:8px">🎯 目標價 {_tp}</span>'
                    st.markdown(f"""
<div style="background:#f0f6ff;border-left:4px solid #4a7fa5;border-radius:6px;padding:12px 16px;margin-bottom:4px">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div style="font-weight:700;font-size:15px">{note['title']}{_tp_html}</div>
    <div style="font-family:monospace;font-size:12px;color:#5B6573">{note['date']}</div>
  </div>
  <div style="margin-top:6px">{tags_html}</div>
</div>""", unsafe_allow_html=True)

                    with st.expander("展開內容與附件", expanded=False):
                        edit_key = f"editing_{nid}"
                        is_editing = st.session_state.get(edit_key, False)

                        if is_editing:
                            # ── 編輯模式 ──
                            e_title  = st.text_input("標題", value=note["title"], key=f"e_title_{nid}")
                            ec1, ec2, ec3 = st.columns([1.5, 1, 1])
                            e_date   = ec1.date_input("日期",
                                value=datetime.date.fromisoformat(note["date"]), key=f"e_date_{nid}")
                            e_target = ec2.number_input("目標價格", min_value=0.0,
                                value=float(note.get("target_price") or 0), step=1.0,
                                format="%.2f", key=f"e_target_{nid}")
                            e_tags   = ec3.text_input("標籤（逗號分隔）",
                                value=", ".join(note.get("tags", [])), key=f"e_tags_{nid}")
                            e_content = st.text_area("內容", value=note.get("content", ""),
                                height=200, key=f"e_content_{nid}")

                            sv_col, cancel_col = st.columns([1, 1])
                            if sv_col.button("💾 儲存修改", key=f"save_edit_{nid}", type="primary"):
                                note["title"]        = e_title.strip()
                                note["date"]         = str(e_date)
                                note["target_price"] = e_target if e_target > 0 else None
                                note["tags"]         = [t.strip() for t in e_tags.split(",") if t.strip()]
                                note["content"]      = e_content.strip()
                                _save_index()
                                st.session_state[edit_key] = False
                                st.rerun()
                            if cancel_col.button("✖ 取消", key=f"cancel_edit_{nid}"):
                                st.session_state[edit_key] = False
                                st.rerun()
                        else:
                            # ── 檢視模式 ──
                            if note.get("content"):
                                st.markdown(
                                    f'<div style="white-space:pre-wrap;line-height:1.7">{note["content"]}</div>',
                                    unsafe_allow_html=True)

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

                            act_col1, act_col2 = st.columns([1, 1])
                            if act_col1.button("✏️ 編輯此筆記", key=f"edit_note_{nid}"):
                                st.session_state[edit_key] = True
                                st.rerun()
                            if act_col2.button("🗑️ 刪除此筆記", key=f"del_note_{nid}"):
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

# ==================== Podcast 整理 ====================
elif page == "🎙️ Podcast 整理":
    import uuid as _uuid
    st.title("🎙️ Podcast 整理")

    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(DATA_DIR, exist_ok=True)
    POD_FILE = os.path.join(DATA_DIR, "podcasts.json")

    if os.path.exists(POD_FILE):
        with open(POD_FILE, "r", encoding="utf-8") as f:
            _pod_raw = json.load(f)
    else:
        _pod_raw = {}

    if isinstance(_pod_raw, list):
        _pod_raw = {"__channels__": [], "episodes": _pod_raw}
    pod_channels: list = _pod_raw.get("__channels__", [])
    pod_db:       list = _pod_raw.get("episodes", [])

    def _pod_save():
        with open(POD_FILE, "w", encoding="utf-8") as f:
            json.dump({"__channels__": pod_channels, "episodes": pod_db},
                      f, ensure_ascii=False, indent=2)

    pod_left, pod_right = st.columns([1, 2.5])

    with pod_left:
        st.subheader("📻 頻道")

        with st.expander("➕ 新增頻道", expanded=len(pod_channels) == 0):
            _new_ch = st.text_input("頻道名稱", placeholder="例如：股癌、財報狗", key="new_channel")
            if st.button("新增", key="add_channel"):
                ch = _new_ch.strip()
                if ch and ch not in pod_channels:
                    pod_channels.append(ch)
                    _pod_save()
                    st.rerun()

        st.divider()

        _fil_tag = st.text_input("🔍 標籤搜尋", placeholder="台積電、升息…", key="pod_tag_filter")

        sel_channel = st.session_state.get("pod_channel", "全部")
        if st.button("📂 全部", key="ch_all", use_container_width=True,
                     type="primary" if sel_channel == "全部" else "secondary"):
            st.session_state["pod_channel"] = "全部"
            st.rerun()

        for ch in pod_channels:
            ep_count = sum(1 for e in pod_db if e.get("podcast") == ch)
            is_sel = sel_channel == ch
            col_ch, col_del = st.columns([4, 1])
            if col_ch.button(f"🎙️ {ch}  ({ep_count})", key=f"ch_{ch}",
                             use_container_width=True,
                             type="primary" if is_sel else "secondary"):
                st.session_state["pod_channel"] = ch
                st.session_state.pop("pod_sel", None)
                st.rerun()
            if col_del.button("🗑", key=f"del_ch_{ch}"):
                pod_channels.remove(ch)
                _pod_save()
                if st.session_state.get("pod_channel") == ch:
                    st.session_state["pod_channel"] = "全部"
                st.rerun()

        st.divider()

        sel_channel = st.session_state.get("pod_channel", "全部")
        filtered = pod_db
        if sel_channel != "全部":
            filtered = [e for e in filtered if e.get("podcast") == sel_channel]
        if _fil_tag.strip():
            filtered = [e for e in filtered if _fil_tag.strip().lower() in
                        " ".join(e.get("tags", [])).lower()]
        filtered = sorted(filtered, key=lambda e: e.get("date", ""), reverse=True)

        if filtered:
            for ep in filtered:
                _ep_label = f"{ep.get('date','')[:10]}　{ep.get('title','')[:18]}"
                if st.button(_ep_label, key=f"pod_sel_{ep['id']}", use_container_width=True):
                    st.session_state["pod_sel"] = ep["id"]
                    st.rerun()
        else:
            st.info("尚無集數")

    with pod_right:
        with st.expander("➕ 新增筆記", expanded=len(pod_db) == 0):
            _pa, _pb = st.columns([1.5, 1])
            if pod_channels:
                _ch_sel = _pa.selectbox("頻道", pod_channels + ["＋ 新頻道"], key="n_pod_ch")
                n_pod   = _pa.text_input("新頻道名稱", key="n_pod_new") if _ch_sel == "＋ 新頻道" else _ch_sel
            else:
                n_pod = _pa.text_input("頻道名稱", placeholder="例如：股癌", key="n_pod_new")
            n_date  = _pb.date_input("收聽日期", value=datetime.date.today(), key="n_pod_date")
            n_title = st.text_input("集數／標題", placeholder="例如：EP123 台積電展望", key="n_pod_title")
            n_link  = st.text_input("連結（選填）", placeholder="https://...", key="n_pod_link")
            n_tags  = st.text_input("標籤（逗號分隔）", placeholder="台積電, 升息", key="n_pod_tags")

            st.markdown("**📊 結構化觀點**")
            _vc1, _vc2 = st.columns(2)
            n_bull  = _vc1.text_area("👆 看多標的", height=80, key="n_bull")
            n_bear  = _vc2.text_area("👇 看空標的", height=80, key="n_bear")
            n_view  = st.text_area("🌍 市場觀點", height=80, key="n_view")
            n_trade = st.text_area("⚡ 操作建議", height=80, key="n_trade")
            st.markdown("**📝 重點摘要**")
            n_notes = st.text_area("自由筆記", height=150, key="n_pod_notes")

            if st.button("💾 儲存", type="primary", key="pod_save"):
                if not n_title.strip():
                    st.warning("請填寫標題")
                elif not n_pod.strip():
                    st.warning("請填寫頻道名稱")
                else:
                    if n_pod.strip() not in pod_channels:
                        pod_channels.append(n_pod.strip())
                    new_ep = {
                        "id":      str(_uuid.uuid4())[:8],
                        "podcast": n_pod.strip(),
                        "title":   n_title.strip(),
                        "date":    str(n_date),
                        "link":    n_link.strip(),
                        "tags":    [t.strip() for t in n_tags.split(",") if t.strip()],
                        "bull":    n_bull.strip(),
                        "bear":    n_bear.strip(),
                        "view":    n_view.strip(),
                        "trade":   n_trade.strip(),
                        "notes":   n_notes.strip(),
                    }
                    pod_db.insert(0, new_ep)
                    _pod_save()
                    st.session_state["pod_sel"] = new_ep["id"]
                    st.rerun()

        st.divider()

        sel_id = st.session_state.get("pod_sel")
        sel_ep = next((e for e in pod_db if e["id"] == sel_id), None)
        if sel_ep is None and pod_db:
            sel_ep = sorted(pod_db, key=lambda e: e.get("date", ""), reverse=True)[0]

        if sel_ep:
            tags_html = " ".join(
                f'<span style="background:#4a7fa5;color:#fff;font-size:11px;padding:2px 8px;border-radius:10px">{t}</span>'
                for t in sel_ep.get("tags", [])
            )
            link_html = (f'<a href="{sel_ep["link"]}" target="_blank" '
                         f'style="font-size:12px;color:#4a7fa5">🔗 原始連結</a>') if sel_ep.get("link") else ""
            st.markdown(f"""
<div style="background:#f0f6ff;border-left:5px solid #4a7fa5;border-radius:8px;padding:16px 18px;margin-bottom:8px">
  <div style="font-size:12px;color:#888;font-family:monospace">{sel_ep.get('podcast','')}　·　{sel_ep.get('date','')}</div>
  <div style="font-size:17px;font-weight:700;margin:4px 0">{sel_ep.get('title','')}</div>
  <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">{tags_html}</div>
  <div style="margin-top:6px">{link_html}</div>
</div>""", unsafe_allow_html=True)

            _v1, _v2 = st.columns(2)
            if sel_ep.get("bull"):
                _v1.markdown(f"**👆 看多標的**\n\n{sel_ep['bull']}")
            if sel_ep.get("bear"):
                _v2.markdown(f"**👇 看空標的**\n\n{sel_ep['bear']}")
            if sel_ep.get("view"):
                st.markdown(f"**🌍 市場觀點**\n\n{sel_ep['view']}")
            if sel_ep.get("trade"):
                st.info(f"⚡ **操作建議**　{sel_ep['trade']}")
            if sel_ep.get("notes"):
                st.markdown("**📝 重點摘要**")
                st.markdown(
                    f'<div style="background:#fafafa;border-radius:6px;padding:12px 16px;'
                    f'font-size:14px;line-height:1.8;white-space:pre-wrap">{sel_ep["notes"]}</div>',
                    unsafe_allow_html=True)

            st.divider()
            if st.button("🗑️ 刪除此筆記", type="secondary", key="pod_del"):
                pod_db[:] = [e for e in pod_db if e["id"] != sel_ep["id"]]
                _pod_save()
                st.session_state.pop("pod_sel", None)
                st.rerun()
        else:
            st.info("左側選擇集數，或點擊上方「新增」開始記錄")
