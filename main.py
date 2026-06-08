import streamlit as st
import requests
import urllib3
import pandas as pd
import datetime
import os
import io
import plotly.graph_objects as go
import xml.etree.ElementTree as ET
from urllib.parse import quote
from streamlit_autorefresh import st_autorefresh
from FinMind.data import DataLoader

urllib3.disable_warnings()

st.set_page_config(page_title="台股交易系統", layout="wide")

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

# 側邊欄選單
st.sidebar.title("📊 台股交易系統")
page = st.sidebar.radio("選擇頁面", ["🏠 選股系統", "🌍 總經儀表板", "📰 新聞監控", "📊 散戶指標"])

# ==================== 選股系統 ====================
if page == "🏠 選股系統":
    st.title("台股動能選股")
    st_autorefresh(interval=20 * 60 * 1000, key="stock_refresh")

    # ------------------------------
    # 每日結果鎖定快取：當天跑過一次後，結果存成檔案，
    # 同一天內重新整理頁面就直接讀檔，不再呼叫 FinMind API，避免浪費 token 額度
    # ------------------------------
    CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
    os.makedirs(CACHE_DIR, exist_ok=True)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    cache_file = os.path.join(CACHE_DIR, f"screener_{today_str}.csv")

    if os.path.exists(cache_file):
        st.success(f"📌 今天（{today_str}）已經跑過選股，直接讀取鎖定的結果，不重新呼叫 API")
        result = pd.read_csv(cache_file)
    else:
        api = DataLoader()
        api.login_by_token(api_token=st.secrets["FINMIND_TOKEN"])

        with st.spinner("今天第一次載入，正在抓取成交值前100名..."):
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
            top100 = df.sort_values("成交金額", ascending=False).head(100).reset_index(drop=True)
            stock_ids = top100["證券代號"].tolist()

        with st.spinner("計算20日均線中，請稍候..."):
            end_date = datetime.date.today().strftime("%Y-%m-%d")
            start_date = (datetime.date.today() - datetime.timedelta(days=40)).strftime("%Y-%m-%d")

            result_list = []
            for sid in stock_ids:
                try:
                    price = api.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=end_date)
                    if len(price) >= 20:
                        price = price.sort_values("date")
                        ma20 = price["close"].iloc[-20:].mean()
                        close = price["close"].iloc[-1]
                        diff_pct = (close - ma20) / ma20 * 100
                        if -3 <= diff_pct <= 3:
                            result_list.append({
                                "證券代號": sid,
                                "20日均線": round(ma20, 2),
                                "收盤價": close,
                                "距均線(%)": round(diff_pct, 2)
                            })
                except:
                    pass

            result = top100.merge(pd.DataFrame(result_list), on="證券代號")
            result = result.sort_values("距均線(%)", key=abs).reset_index(drop=True)

        # 鎖定結果：存成當天的快取檔，之後重新整理就不用再打 API
        result.to_csv(cache_file, index=False, encoding="utf-8-sig")
        st.success(f"✅ 選股結果已鎖定並存檔（{cache_file}），今天內重新整理將直接讀取，不再消耗 API 額度")

    result.index = range(1, len(result) + 1)

    st.subheader(f"資料日期：{today_str}　符合條件：{len(result)} 檔")
    st.dataframe(result[["證券代號", "證券名稱", "成交金額(億)", "收盤價_x", "20日均線", "距均線(%)"]], use_container_width=True)

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
            if df_r.empty:
                st.warning(f"目前無法取得{label}三大法人資料，請稍後再試。")
                return

            latest_r = df_r.iloc[-1]
            net = latest_r["三大法人合計淨OI"]
            direction = "偏多（淨多單）" if net > 0 else ("偏空（淨空單）" if net < 0 else "持平")

            if len(df_r) >= 2:
                prev_r = df_r.iloc[-2]
                delta_val = net - prev_r["三大法人合計淨OI"]
                st.metric(f"{label} 三大法人合計淨部位（{direction}）", f"{int(net):,} 口",
                          delta=f"{int(delta_val):,}（較前一日）")
            else:
                st.metric(f"{label} 三大法人合計淨部位（{direction}）", f"{int(net):,} 口")

            fig_r = go.Figure()
            fig_r.add_trace(go.Scatter(x=df_r["日期"], y=df_r["三大法人合計淨OI"], name="三大法人合計淨部位", line=dict(color=color)))
            fig_r.add_hline(y=0, line_dash="dot", line_color="gray")
            fig_r.update_layout(title=f"三大法人合計淨部位趨勢 - {label}（近20個交易日，正值=偏多／負值=偏空）",
                                xaxis_title="日期", yaxis_title="淨部位（口）", hovermode="x unified")
            st.plotly_chart(fig_r, use_container_width=True)

            df_r_diff = df_r.copy()
            df_r_diff["三大法人淨部位日變化"] = df_r_diff["三大法人合計淨OI"].diff()
            df_r_diff = df_r_diff.dropna(subset=["三大法人淨部位日變化"])
            if not df_r_diff.empty:
                fig_r_diff = go.Figure()
                fig_r_diff.add_trace(go.Bar(
                    x=df_r_diff["日期"], y=df_r_diff["三大法人淨部位日變化"], name="三大法人淨部位較前一日變化",
                    marker_color=["crimson" if v < 0 else "seagreen" for v in df_r_diff["三大法人淨部位日變化"]]
                ))
                fig_r_diff.add_hline(y=0, line_dash="dot", line_color="gray")
                fig_r_diff.update_layout(title=f"三大法人合計淨部位「較前一日」變化量 - {label}",
                                         xaxis_title="日期", yaxis_title="變化量（口）", hovermode="x unified")
                st.plotly_chart(fig_r_diff, use_container_width=True)

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
                df_pc_diff = df_pc.copy()
                df_pc_diff["成交量比率日變化"] = df_pc_diff["買賣權成交量比率%"].diff()
                df_pc_diff["未平倉量比率日變化"] = df_pc_diff["買賣權未平倉量比率%"].diff()
                df_pc_diff = df_pc_diff.dropna(subset=["成交量比率日變化"])
                if not df_pc_diff.empty:
                    fig_pc_diff = go.Figure()
                    fig_pc_diff.add_trace(go.Bar(x=df_pc_diff["日期"], y=df_pc_diff["成交量比率日變化"], name="成交量比率較前一日變化"))
                    fig_pc_diff.add_trace(go.Bar(x=df_pc_diff["日期"], y=df_pc_diff["未平倉量比率日變化"], name="未平倉量比率較前一日變化"))
                    fig_pc_diff.add_hline(y=0, line_dash="dot", line_color="gray")
                    fig_pc_diff.update_layout(title="Put/Call Ratio「較前一日」變化量", barmode="group",
                                              xaxis_title="日期", yaxis_title="變化量（百分點）", hovermode="x unified")
                    st.plotly_chart(fig_pc_diff, use_container_width=True)
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

            df_inst_diff = df_inst.copy()
            for col in ["自營商淨OI", "投信淨OI", "外資淨OI"]:
                df_inst_diff[f"{col}_變化"] = df_inst_diff[col].diff()
            df_inst_diff = df_inst_diff.dropna(subset=["自營商淨OI_變化"])
            if not df_inst_diff.empty:
                fig_inst_diff = go.Figure()
                fig_inst_diff.add_trace(go.Bar(x=df_inst_diff["日期"], y=df_inst_diff["自營商淨OI_變化"], name="自營商較前一日變化"))
                fig_inst_diff.add_trace(go.Bar(x=df_inst_diff["日期"], y=df_inst_diff["投信淨OI_變化"], name="投信較前一日變化"))
                fig_inst_diff.add_trace(go.Bar(x=df_inst_diff["日期"], y=df_inst_diff["外資淨OI_變化"], name="外資較前一日變化"))
                fig_inst_diff.add_hline(y=0, line_dash="dot", line_color="gray")
                fig_inst_diff.update_layout(title="三大法人淨部位「較前一日」變化量", barmode="group",
                                            xaxis_title="日期", yaxis_title="變化量（口）", hovermode="x unified")
                st.plotly_chart(fig_inst_diff, use_container_width=True)

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

            df_margin_diff = df_margin.copy()
            df_margin_diff["融資餘額日變化"] = df_margin_diff["融資餘額"].diff()
            df_margin_diff = df_margin_diff.dropna(subset=["融資餘額日變化"])
            if not df_margin_diff.empty:
                fig_margin_diff = go.Figure()
                fig_margin_diff.add_trace(go.Bar(
                    x=df_margin_diff["日期"], y=df_margin_diff["融資餘額日變化"], name="融資餘額較前一日變化",
                    marker_color=["crimson" if v < 0 else "seagreen" for v in df_margin_diff["融資餘額日變化"]]
                ))
                fig_margin_diff.add_hline(y=0, line_dash="dot", line_color="gray")
                fig_margin_diff.update_layout(title="融資餘額「較前一日」變化量", xaxis_title="日期", yaxis_title="變化量（仟元）", hovermode="x unified")
                st.plotly_chart(fig_margin_diff, use_container_width=True)