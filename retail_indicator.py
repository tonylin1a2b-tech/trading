import streamlit as st
import requests
import urllib3
import pandas as pd
import io
import datetime
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

urllib3.disable_warnings()

st.set_page_config(page_title="散戶指標", layout="wide")
st.title("📊 大盤散戶指標")
st.caption("資料來源：台灣期貨交易所（TAIFEX）、證交所（TWSE）｜ 散戶部位為「推算值」（總未平倉 − 三大法人合計），僅供參考，非專業投資建議")

# 每 30 分鐘自動更新
st_autorefresh(interval=30 * 60 * 1000, key="retail_refresh")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
}


def recent_trading_dates(n_days: int = 30):
    """產生最近 n_days 個可能的交易日（排除週末，國定假日會在抓取時自動跳過）"""
    today = datetime.date.today()
    dates = []
    d = today
    while len(dates) < n_days:
        if d.weekday() < 5:  # 週一~週五
            dates.append(d)
        d -= datetime.timedelta(days=1)
    return list(reversed(dates))


@st.cache_data(ttl=60 * 60 * 4)
def fetch_futures_institutional(date_str: str, commodity_id: str):
    """抓取 TAIFEX 指定日期、指定商品的三大法人期貨多空部位資料
    回傳 dict：{自營商淨OI, 投信淨OI, 外資淨OI, 三大法人合計淨OI, 全市場合計淨OI, 散戶推算淨OI}
    若當日無資料（例如假日）則回傳 None
    """
    url = "https://www.taifex.com.tw/cht/3/futContractsDate"
    payload = {
        "queryType": "1",
        "goDay": "",
        "doQuery": "1",
        "dateaddcnt": "",
        "queryDate": date_str,
        "commodityId": commodity_id,
    }
    try:
        res = requests.post(url, headers=HEADERS, data=payload, verify=False, timeout=15)
        res.encoding = "utf-8"
        tables = pd.read_html(io.StringIO(res.text))
        if not tables:
            return None
        t = tables[0]
        if len(t) < 7:
            return None

        # 欄位位置（依 TAIFEX 表格固定結構）：
        # col 2 = 身份別, col 13 = 未平倉餘額-多空淨額-口數
        idcol = t.iloc[:, 2].astype(str)
        oi_net = pd.to_numeric(t.iloc[:, 13], errors="coerce")

        def get_net(identity):
            mask = idcol == identity
            vals = oi_net[mask]
            return float(vals.iloc[0]) if len(vals) > 0 else 0.0

        dealer = get_net("自營商")
        ita = get_net("投信")
        foreign = get_net("外資")
        total = float(oi_net.iloc[-1])  # 最後一列為「期貨合計」

        institutional_sum = dealer + ita + foreign
        retail_est = total - institutional_sum

        return {
            "日期": date_str,
            "自營商淨OI": dealer,
            "投信淨OI": ita,
            "外資淨OI": foreign,
            "三大法人合計淨OI": institutional_sum,
            "全市場合計淨OI": total,
            "散戶推算淨OI": retail_est,
        }
    except Exception:
        return None


@st.cache_data(ttl=60 * 60 * 4)
def fetch_institutional_trend(commodity_id: str, n_days: int = 20) -> pd.DataFrame:
    """逐日抓取近 n_days 個交易日的三大法人/散戶推算淨部位，組成趨勢資料"""
    rows = []
    for d in recent_trading_dates(n_days):
        date_str = d.strftime("%Y/%m/%d")
        data = fetch_futures_institutional(date_str, commodity_id)
        if data:
            rows.append(data)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["日期"] = pd.to_datetime(df["日期"], format="%Y/%m/%d")
    return df.sort_values("日期").reset_index(drop=True)


@st.cache_data(ttl=60 * 60 * 4)
def fetch_pc_ratio() -> pd.DataFrame:
    """抓取台指選擇權 Put/Call Ratio（買賣權成交量比、未平倉量比），近期約 20 個交易日"""
    url = "https://www.taifex.com.tw/cht/3/pcRatio"
    res = requests.get(url, headers=HEADERS, verify=False, timeout=15)
    res.encoding = "utf-8"
    tables = pd.read_html(io.StringIO(res.text))
    df = tables[0]
    df["日期"] = pd.to_datetime(df["日期"], format="%Y/%m/%d")
    return df.sort_values("日期").reset_index(drop=True)


@st.cache_data(ttl=60 * 60 * 4)
def fetch_margin_balance(date_str: str):
    """抓取證交所上市個股融資融券餘額加總（全市場），date_str 格式為 YYYYMMDD"""
    url = f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={date_str}&selectType=ALL&response=json"
    try:
        res = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        data = res.json()
        if data.get("stat") != "OK":
            return None
        tables = data.get("tables", [])
        if not tables:
            return None
        rows = tables[0].get("data", [])
        # 找「融資金額(億)合計」列：欄位通常為 [項目, 買進, 賣出, 現金(券)償還, 前日餘額, 今日餘額]
        margin_balance_total = None
        for r in rows:
            if "合計" in r[0]:
                margin_balance_total = r
                break
        if margin_balance_total is None and rows:
            margin_balance_total = rows[0]
        return {
            "日期": date_str,
            "今日餘額": pd.to_numeric(str(margin_balance_total[-1]).replace(",", ""), errors="coerce"),
            "前日餘額": pd.to_numeric(str(margin_balance_total[-2]).replace(",", ""), errors="coerce"),
        }
    except Exception:
        return None


@st.cache_data(ttl=60 * 60 * 4)
def fetch_margin_trend(n_days: int = 20) -> pd.DataFrame:
    """逐日抓取近 n_days 個交易日的融資餘額，組成趨勢資料"""
    rows = []
    for d in recent_trading_dates(n_days):
        date_str = d.strftime("%Y%m%d")
        data = fetch_margin_balance(date_str)
        if data and pd.notna(data["今日餘額"]):
            rows.append({"日期": d, "融資餘額": data["今日餘額"]})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["日期"] = pd.to_datetime(df["日期"])
    return df.sort_values("日期").reset_index(drop=True)


# ------------------------------
# 1. 散戶多空淨部位估算（小台指）
# ------------------------------
st.subheader("🟢🔴 散戶多空淨部位估算（小型臺指期貨）")
st.caption("推算邏輯：小台指全市場未平倉淨額 − 三大法人（自營商+投信+外資）合計淨額 ≈ 散戶淨部位｜散戶通常被視為「反指標」：散戶大幅淨多單時市場可能偏向過熱，淨空單時則可能偏向過度悲觀")

with st.spinner("載入散戶部位推算趨勢中（首次載入需逐日查詢，請稍候）..."):
    df_retail = fetch_institutional_trend("MXF", n_days=20)

    if df_retail.empty:
        st.warning("目前無法取得小台指三大法人資料，請稍後再試。")
    else:
        latest = df_retail.iloc[-1]
        col1, col2, col3 = st.columns(3)
        col1.metric("散戶推算淨部位（口）", f"{int(latest['散戶推算淨OI']):,}")
        col2.metric("三大法人合計淨部位（口）", f"{int(latest['三大法人合計淨OI']):,}")
        col3.metric("全市場合計淨部位（口）", f"{int(latest['全市場合計淨OI']):,}")

        fig_retail = go.Figure()
        fig_retail.add_trace(go.Scatter(x=df_retail["日期"], y=df_retail["散戶推算淨OI"], name="散戶推算淨部位", line=dict(color="orange")))
        fig_retail.add_trace(go.Scatter(x=df_retail["日期"], y=df_retail["三大法人合計淨OI"], name="三大法人合計淨部位", line=dict(color="royalblue")))
        fig_retail.add_hline(y=0, line_dash="dot", line_color="gray")
        fig_retail.update_layout(
            title="散戶 vs 三大法人 淨部位趨勢（近20個交易日）",
            xaxis_title="日期", yaxis_title="淨部位（口）", hovermode="x unified"
        )
        st.plotly_chart(fig_retail, use_container_width=True)

st.divider()

# ------------------------------
# 2. Put/Call Ratio
# ------------------------------
st.subheader("📈 選擇權 Put/Call Ratio（籌碼面氣氛指標）")
st.caption("比率越高代表賣權（put）相對買權（call）的量能/未平倉越大，市場避險或看空情緒較濃；比率越低則反映看多氣氛較濃")

with st.spinner("載入 Put/Call Ratio 中..."):
    try:
        df_pc = fetch_pc_ratio()
        if df_pc.empty:
            st.info("目前查無 Put/Call Ratio 資料")
        else:
            latest_pc = df_pc.iloc[-1]
            col1, col2 = st.columns(2)
            col1.metric("買賣權成交量比率 (%)", f"{latest_pc['買賣權成交量比率%']:.2f}")
            col2.metric("買賣權未平倉量比率 (%)", f"{latest_pc['買賣權未平倉量比率%']:.2f}")

            fig_pc = go.Figure()
            fig_pc.add_trace(go.Scatter(x=df_pc["日期"], y=df_pc["買賣權成交量比率%"], name="成交量 Put/Call Ratio"))
            fig_pc.add_trace(go.Scatter(x=df_pc["日期"], y=df_pc["買賣權未平倉量比率%"], name="未平倉量 Put/Call Ratio"))
            fig_pc.add_hline(y=100, line_dash="dot", line_color="gray")
            fig_pc.update_layout(
                title="Put/Call Ratio 趨勢", xaxis_title="日期", yaxis_title="比率 (%)", hovermode="x unified"
            )
            st.plotly_chart(fig_pc, use_container_width=True)
    except Exception as e:
        st.warning(f"Put/Call Ratio 載入失敗，請稍後再試。({e})")

st.divider()

# ------------------------------
# 3. 三大法人台指期貨淨部位趨勢（大台）
# ------------------------------
st.subheader("🏦 三大法人台指期貨淨部位趨勢（大台指）")
st.caption("自營商／投信／外資在「臺股期貨」未平倉淨部位的多空變化，反映法人對大盤中長期方向的籌碼佈局")

with st.spinner("載入三大法人淨部位趨勢中..."):
    df_inst = fetch_institutional_trend("TXF", n_days=20)

    if df_inst.empty:
        st.warning("目前無法取得三大法人資料，請稍後再試。")
    else:
        fig_inst = go.Figure()
        fig_inst.add_trace(go.Scatter(x=df_inst["日期"], y=df_inst["自營商淨OI"], name="自營商"))
        fig_inst.add_trace(go.Scatter(x=df_inst["日期"], y=df_inst["投信淨OI"], name="投信"))
        fig_inst.add_trace(go.Scatter(x=df_inst["日期"], y=df_inst["外資淨OI"], name="外資"))
        fig_inst.add_hline(y=0, line_dash="dot", line_color="gray")
        fig_inst.update_layout(
            title="三大法人臺股期貨淨部位趨勢（近20個交易日）",
            xaxis_title="日期", yaxis_title="淨部位（口）", hovermode="x unified"
        )
        st.plotly_chart(fig_inst, use_container_width=True)

st.divider()

# ------------------------------
# 4. 融資餘額走勢
# ------------------------------
st.subheader("💰 上市股票融資餘額走勢")
st.caption("融資餘額增加，通常反映散戶（使用槓桿）追價意願提升；融資餘額減少則可能代表散戶信心轉弱或遭斷頭")

with st.spinner("載入融資餘額趨勢中（首次載入需逐日查詢，請稍候）..."):
    df_margin = fetch_margin_trend(n_days=20)

    if df_margin.empty:
        st.warning("目前無法取得融資餘額資料，請稍後再試。")
    else:
        fig_margin = go.Figure()
        fig_margin.add_trace(go.Scatter(x=df_margin["日期"], y=df_margin["融資餘額"], name="融資餘額（仟元）", line=dict(color="green")))
        fig_margin.update_layout(
            title="上市股票融資餘額趨勢（近20個交易日）",
            xaxis_title="日期", yaxis_title="融資餘額（仟元）", hovermode="x unified"
        )
        st.plotly_chart(fig_margin, use_container_width=True)
