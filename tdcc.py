"""
TDCC 集保戶股數分級 — 大戶持股比例監控
資料來源: opendata.tdcc.com.tw (免費、每週三更新)
本地儲存: data/tdcc_history.json，每次抓到新日期自動附加
"""
import json, os, io, warnings
import requests
import pandas as pd
import streamlit as st

warnings.filterwarnings("ignore")

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "tdcc_history.json")

# 持股分級對照表
LEVEL_LABELS = {
    1:  "1~999",
    2:  "1,000~5,000",
    3:  "5,001~10,000",
    4:  "10,001~15,000",
    5:  "15,001~20,000",
    6:  "20,001~30,000",
    7:  "30,001~40,000",
    8:  "40,001~50,000",
    9:  "50,001~100,000",
    10: "100,001~200,000",
    11: "200,001~400,000",
    12: "400,001~600,000",
    13: "600,001~800,000",
    14: "800,001~1,000,000",
    15: "1,000,001以上",
}

# 大戶 = level 10~15 (100,001股以上)
BIG_LEVEL_MIN = 10
BIG_LEVEL_MAX = 15


@st.cache_data(ttl=3600)
def fetch_tdcc_latest() -> pd.DataFrame:
    """抓取最新一期集保戶股數分級全市場資料，回傳 DataFrame。"""
    r = requests.get(
        "https://opendata.tdcc.com.tw/getOD.ashx",
        params={"id": "1-5"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30, verify=False,
    )
    r.raise_for_status()
    text = r.content.decode("utf-8-sig")
    df = pd.read_csv(io.StringIO(text))
    df.columns = ["date", "stock_id", "level", "holders", "shares", "pct"]
    df["stock_id"] = df["stock_id"].astype(str).str.strip()
    return df


def calc_metrics(df: pd.DataFrame, stock_id: str) -> dict | None:
    """
    計算單一股票的大戶持股指標。
    回傳 dict 或 None（無資料）。
    """
    s = df[df["stock_id"] == stock_id.strip()].copy()
    if s.empty:
        return None
    total_row = s[s["level"] == 17]
    if total_row.empty:
        return None
    total_shares = int(total_row["shares"].values[0])
    total_holders = int(total_row["holders"].values[0])
    if total_shares == 0:
        return None

    big = s[(s["level"] >= BIG_LEVEL_MIN) & (s["level"] <= BIG_LEVEL_MAX)]
    big_shares  = int(big["shares"].sum())
    big_holders = int(big["holders"].sum())
    big_pct     = round(big_shares / total_shares * 100, 2)

    # 散戶 (level 1, 1~999 股)
    tiny = s[s["level"] == 1]
    tiny_holders = int(tiny["holders"].values[0]) if not tiny.empty else 0

    # 分布 (level 1~15)
    dist = []
    for _, row in s[s["level"].between(1, 15)].iterrows():
        dist.append({
            "level": int(row["level"]),
            "label": LEVEL_LABELS.get(int(row["level"]), ""),
            "holders": int(row["holders"]),
            "shares": int(row["shares"]),
            "pct": float(row["pct"]),
        })

    return {
        "date": str(s["date"].values[0]),
        "stock_id": stock_id,
        "big_pct": big_pct,
        "big_holders": big_holders,
        "big_shares": big_shares,
        "total_shares": total_shares,
        "total_holders": total_holders,
        "tiny_holders": tiny_holders,
        "dist": dist,
    }


def load_history() -> dict:
    """從本地 JSON 讀取歷史記錄。"""
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_snapshot(metrics: dict):
    """把一筆新的 metrics 存入歷史 JSON（若同一日期已存在則跳過）。"""
    history = load_history()
    sid = metrics["stock_id"]
    date = metrics["date"]

    if sid not in history:
        history[sid] = []

    existing_dates = {r["date"] for r in history[sid]}
    if date not in existing_dates:
        history[sid].append({
            "date": date,
            "big_pct": metrics["big_pct"],
            "big_holders": metrics["big_holders"],
            "tiny_holders": metrics["tiny_holders"],
        })
        history[sid].sort(key=lambda x: x["date"])
        os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)


def get_history(stock_id: str) -> list:
    """回傳某股票的歷史列表 (date, big_pct, big_holders, tiny_holders)。"""
    return load_history().get(stock_id.strip(), [])
