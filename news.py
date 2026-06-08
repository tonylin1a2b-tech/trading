import streamlit as st
import requests
import urllib3
import xml.etree.ElementTree as ET
import pandas as pd
from urllib.parse import quote
from streamlit_autorefresh import st_autorefresh

urllib3.disable_warnings()

st.set_page_config(page_title="新聞關鍵字監控", layout="wide")
st.title("📰 新聞關鍵字監控")

# 每小時自動更新一次（新聞更新頻率不需要太頻繁，避免過度爬取）
st_autorefresh(interval=60 * 60 * 1000, key="news_refresh")

# ------------------------------
# 監控關鍵字（可自行增減）
# 每個顯示名稱對應一組「中文 + 英文」搜尋詞，會分別查詢後合併結果
# ------------------------------
KEYWORDS = {
    "流動性": ["流動性", "liquidity"],
    "IPO": ["IPO", "首次公開發行"],
    "總經": ["總經", "總體經濟", "macro economy"],
    "戰爭": ["戰爭", "war", "衝突"],
}

# ------------------------------
# 利多 / 利空 關鍵字規則（簡易版規則式情緒分類）
# ------------------------------
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
    """簡易規則式利多/利空分類：依標題中出現的關鍵字數量判斷"""
    bull_score = sum(1 for w in BULLISH_WORDS if w in title)
    bear_score = sum(1 for w in BEARISH_WORDS if w in title)
    if bull_score > bear_score:
        return "🟢 利多"
    elif bear_score > bull_score:
        return "🔴 利空"
    else:
        return "⚪ 中性"


def _is_english(text: str) -> bool:
    """簡單判斷搜尋詞是否為英文（純 ASCII），用來決定要查詢哪個語系/地區的 Google News"""
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _fetch_one(query: str, limit: int) -> list:
    """查詢單一關鍵字（中文或英文）的 Google News RSS 結果
    使用 Google News 的 when:1d 語法，讓伺服器端直接回傳近 24 小時內的新聞，
    避免只抓前面幾筆就被用戶端日期篩選掉、導致筆數過少的問題。

    若搜尋詞為英文，改用美國/英文語系（hl=en-US&gl=US&ceid=US:en）查詢，
    這樣才能搜到主流英文媒體（Reuters、Bloomberg、Yahoo Finance、CNBC...等），
    而不是只搜到台灣繁中媒體轉載的英文新聞。
    """
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
            "時間": time_str,
            "標題": title,
            "來源": source_name,
            "情緒": classify_sentiment(title),
            "連結": link,
            "_sort": sort_key,
        })
    return rows


@st.cache_data(ttl=60 * 60)  # 快取 1 小時，降低爬取頻率
def fetch_news(queries: list, fetch_limit: int = 40, display_limit: int = 25) -> pd.DataFrame:
    """以「中文 + 英文」多組關鍵字分別搜尋 Google News RSS（已加上 when:1d 限定近24小時），
    合併、去重、依時間排序後回傳前 display_limit 則。"""
    all_rows = []
    for q in queries:
        all_rows.extend(_fetch_one(q, fetch_limit))

    if not all_rows:
        return pd.DataFrame(columns=["時間", "標題", "來源", "情緒", "連結"])

    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset=["標題"])  # 去除中英文搜尋重複命中的新聞

    # 保險起見再次確認 24 小時內（理論上 when:1d 已篩過，但避免極少數時區誤差）
    cutoff = pd.Timestamp.now(tz="Asia/Taipei") - pd.Timedelta(hours=24)
    df = df[df["_sort"] >= cutoff]

    df = df.sort_values("_sort", ascending=False).head(display_limit)
    df = df.drop(columns=["_sort"]).reset_index(drop=True)
    return df


# ------------------------------
# 台美股相關性篩選關鍵字
# 用來從所有抓到的新聞中，挑出跟「台股／美股」較相關的部分送給 AI 摘要
# ------------------------------
TW_US_STOCK_KEYWORDS = [
    "台股", "台積電", "台灣50", "0050", "上市", "上櫃", "櫃買", "證交所", "台指期",
    "美股", "那斯達克", "NASDAQ", "道瓊", "S&P", "標普", "費半", "美國股市",
    "輝達", "NVIDIA", "蘋果", "Apple", "特斯拉", "Tesla", "微軟", "Microsoft",
    "聯準會", "Fed", "FOMC", "升息", "降息", "殖利率", "美元", "台幣",
    "那斯達克100", "美國經濟", "美債", "那指", "費城半導體",
]


def filter_relevant_for_summary(df_all: pd.DataFrame) -> pd.DataFrame:
    """從合併後的新聞中，篩選出標題包含「台股／美股」相關關鍵字的部分"""
    if df_all is None or len(df_all) == 0:
        return df_all
    mask = df_all["標題"].apply(lambda t: any(kw in t for kw in TW_US_STOCK_KEYWORDS))
    return df_all[mask].reset_index(drop=True)


# ------------------------------
# 主畫面：依關鍵字分頁顯示
# ------------------------------
st.caption("資料來源：Google News RSS（每小時自動更新一次，僅顯示近 24 小時內新聞）｜ 情緒分類為「規則式關鍵字比對」，僅供參考，非專業投資建議")

# ------------------------------
# 📋 匯出台美股相關新聞給 AI 判讀（手動複製貼上版本，不需要 API key）
# ------------------------------
st.subheader("📋 匯出台美股相關新聞給 AI 判讀")
st.caption("不需要 API key：篩選出跟台美股相關的新聞後，整理成文字，複製貼到與 Claude 的對話視窗，即可請 AI 幫你分析摘要、標註利多利空")

with st.spinner("正在篩選台美股相關新聞..."):
    try:
        all_news_frames = []
        for label, queries in KEYWORDS.items():
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

tabs = st.tabs([f"🔍 {label}" for label in KEYWORDS])

for tab, (label, queries) in zip(tabs, KEYWORDS.items()):
    with tab:
        st.caption(f"搜尋詞：{'、'.join(queries)}")
        with st.spinner(f"載入「{label}」相關新聞（中英文搜尋）..."):
            try:
                df_news = fetch_news(queries, fetch_limit=40, display_limit=25)

                if len(df_news) == 0:
                    st.info("目前查無相關新聞")
                else:
                    # 統計利多/利空分布
                    bull_count = (df_news["情緒"] == "🟢 利多").sum()
                    bear_count = (df_news["情緒"] == "🔴 利空").sum()
                    neutral_count = (df_news["情緒"] == "⚪ 中性").sum()

                    col1, col2, col3 = st.columns(3)
                    col1.metric("🟢 利多新聞", f"{bull_count} 則")
                    col2.metric("🔴 利空新聞", f"{bear_count} 則")
                    col3.metric("⚪ 中性新聞", f"{neutral_count} 則")

                    # 顯示新聞列表（含可點擊連結）
                    for _, row in df_news.iterrows():
                        st.markdown(
                            f"**{row['情緒']}** | {row['時間']} | {row['來源']}  \n"
                            f"[{row['標題']}]({row['連結']})"
                        )
                        st.divider()

            except Exception as e:
                st.warning(f"新聞載入失敗，請稍後再試。({e})")
