# services/news.py — 新聞抓取與情緒分類（Google News RSS）

from urllib.parse import quote
import xml.etree.ElementTree as ET

import pandas as pd
import streamlit as st

from utils.http import safe_request


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

_NEWS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}


def classify_sentiment(title: str) -> str:
    bull = sum(1 for w in BULLISH_WORDS if w in title)
    bear = sum(1 for w in BEARISH_WORDS if w in title)
    if bull > bear:
        return "🟢 利多"
    elif bear > bull:
        return "🔴 利空"
    return "⚪ 中性"


def _is_english(text: str) -> bool:
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _fetch_one_news(query: str, limit: int, _dh=None) -> list:
    if _is_english(query):
        locale_params = "hl=en-US&gl=US&ceid=US:en"
    else:
        locale_params = "hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    url = f"https://news.google.com/rss/search?q={quote(query + ' when:1d')}&{locale_params}"
    res = safe_request(url, headers=_NEWS_HEADERS)
    if res is None:
        if _dh:
            _dh.record("Google News", ok=False)
        return []
    if _dh:
        _dh.record("Google News", ok=True)
    root = ET.fromstring(res.content)
    items = root.findall(".//item")[:limit]
    rows = []
    for it in items:
        title = it.findtext("title", "")
        link  = it.findtext("link", "")
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
def fetch_news(queries: tuple, fetch_limit: int = 40, display_limit: int = 25) -> pd.DataFrame:
    """抓取多組關鍵字的 Google News，去重後依時間排序"""
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
