import streamlit as st
import requests
import urllib3
import pandas as pd
import datetime
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
urllib3.disable_warnings()

st.set_page_config(page_title="總經儀表板", layout="wide")
st.title("總經儀表板")

# 每20分鐘自動更新
st_autorefresh(interval=20 * 60 * 1000, key="macro_refresh")

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

# Fed 升降息機率
st.subheader("🇺🇸 Fed 升降息預期")
with st.spinner("載入中..."):
    fed_data = get_fed_probability()
    st.dataframe(fed_data, use_container_width=True)

# Fed 隱含利率趨勢
st.subheader("📈 Fed 隱含利率趨勢（近3個月）")
with st.spinner("載入趨勢圖..."):
    df_jul = get_history("ZQN26.CBT", "7月會議")
    df_sep = get_history("ZQU26.CBT", "9月會議")
    df_nov = get_history("ZQX26.CBT", "11月會議")

    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df_jul["date"], y=df_jul["7月會議"], name="7月會議"))
    fig1.add_trace(go.Scatter(x=df_sep["date"], y=df_sep["9月會議"], name="9月會議"))
    fig1.add_trace(go.Scatter(x=df_nov["date"], y=df_nov["11月會議"], name="11月會議"))
    fig1.update_layout(
        title="Fed 隱含利率趨勢",
        xaxis_title="日期",
        yaxis_title="隱含利率 (%)",
        hovermode="x unified"
    )
    st.plotly_chart(fig1, use_container_width=True)

# 日銀公債ETF趨勢
st.subheader("🇯🇵 日銀政策方向（日本公債ETF趨勢）")
st.caption("ETF價格上漲 = 殖利率下降 = 市場預期不升息｜ETF價格下跌 = 市場預期升息")
st.info("🗓️ 下次日銀會議：2026年6月16日〜17日")

with st.spinner("載入日銀趨勢圖..."):
    df_boj = get_boj_history()
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df_boj["date"], y=df_boj["JGB_ETF"], name="日本公債ETF"))
    fig2.update_layout(
        title="日本公債ETF價格趨勢",
        xaxis_title="日期",
        yaxis_title="ETF 價格 (JPY)",
        hovermode="x unified"
    )
    st.plotly_chart(fig2, use_container_width=True)

# 總經行事曆
st.subheader("📅 重要總經事件（今天起一週內）")
st.caption("註：資料來源僅提供「未來」事件的預測值/前值，無法提供已公布的「實際值」與「過去一週」事件")

event_translate = {
    "CPI": "消費者物價指數",
    "Core CPI": "核心CPI",
    "PPI": "生產者物價指數",
    "Core PPI": "核心PPI",
    "GDP": "國內生產總值",
    "Non-Farm Employment Change": "非農就業人數變化",
    "Non-Farm Payrolls": "非農就業人數",
    "Unemployment Rate": "失業率",
    "Federal Funds Rate": "聯邦基金利率",
    "FOMC Statement": "FOMC聲明",
    "FOMC Press Conference": "FOMC記者會",
    "FOMC Member": "FOMC官員",
    "Interest Rate Decision": "利率決議",
    "Monetary Policy Statement": "貨幣政策聲明",
    "Retail Sales": "零售銷售",
    "Core Retail Sales": "核心零售銷售",
    "ISM Manufacturing PMI": "ISM製造業PMI",
    "ISM Services PMI": "ISM服務業PMI",
    "Manufacturing PMI": "製造業PMI",
    "Services PMI": "服務業PMI",
    "Trade Balance": "貿易帳",
    "Initial Jobless Claims": "初領失業救濟金人數",
    "Building Permits": "建築許可",
    "Housing Starts": "新屋開工",
    "Consumer Confidence": "消費者信心指數",
    "Prelim UoM Consumer Sentiment": "密大消費者信心初值",
    "JOLTS Job Openings": "職位空缺數",
    "ADP Non-Farm Employment Change": "ADP非農就業變化",
    "Average Hourly Earnings": "平均時薪",
    "Bank Holiday": "銀行假日",
    "OPEC Meetings": "OPEC會議",
    "OPEC-JMMC Meetings": "OPEC部長級會議",
    "GDP q/q": "GDP季增率",
    "Press Conference": "記者會",
    "Crude Oil Inventories": "原油庫存",
    "Natural Gas Storage": "天然氣庫存",
}

country_translate = {
    "USD": "🇺🇸 美元", "JPY": "🇯🇵 日圓", "EUR": "🇪🇺 歐元",
    "GBP": "🇬🇧 英鎊", "AUD": "🇦🇺 澳幣", "CAD": "🇨🇦 加幣",
    "NZD": "🇳🇿 紐幣", "CHF": "🇨🇭 瑞郎", "CNY": "🇨🇳 人民幣",
    "All": "🌍 全球",
}

def translate_event(title):
    if title in event_translate:
        return event_translate[title]
    for en, zh in event_translate.items():
        if en in title:
            return title.replace(en, zh)
    return title

with st.spinner("載入行事曆..."):
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(url, headers=headers, verify=False, timeout=10)
        events = res.json()

        df_cal = pd.DataFrame(events)
        df_cal["date"] = pd.to_datetime(df_cal["date"]).dt.tz_convert("Asia/Taipei")

        # 只保留高影響事件
        df_cal = df_cal[df_cal["impact"] == "High"]

        df_cal["時間"] = df_cal["date"].dt.strftime("%m/%d %H:%M")
        df_cal["事件"] = df_cal["title"].apply(translate_event)
        df_cal["幣種"] = df_cal["country"].map(country_translate).fillna(df_cal["country"])
        df_cal = df_cal.rename(columns={"forecast": "預測值", "previous": "前值"})
        df_cal["影響程度"] = "🔴 高"
        df_cal = df_cal.sort_values("date").reset_index(drop=True)
        df_cal.index += 1

        if len(df_cal) > 0:
            st.dataframe(df_cal[["時間", "幣種", "事件", "影響程度", "預測值", "前值"]], use_container_width=True)
        else:
            st.info("近期無高重要性總經事件")

    except Exception as e:
        st.warning(f"行事曆暫時無法載入，請稍後再試。({e})")