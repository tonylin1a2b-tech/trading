"""
YouTube 頻道自動監控 + Gemini 整理腳本
每天執行一次，檢查各頻道新影片，抓字幕並用 Gemini 整理，存入 Google Sheets
"""
import json
import os
import re
import sys
import time
import datetime
import uuid
import requests
import yt_dlp

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def extract_json_obj(text):
    """從 Gemini 回應中解析出 JSON 物件，容忍 code fence 或前後夾雜的說明文字。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


# ── 設定 ──────────────────────────────────────────────────────────────────
CHANNELS = [
    "https://www.youtube.com/@macromicrom2843",
    "https://www.youtube.com/@NaNaShuoMeiGu",
    "https://www.youtube.com/@yutinghaofinance",
    "https://www.youtube.com/@goodfinance",
    "https://www.youtube.com/@richtohappy",
]

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COOKIES_FILE = os.path.join(BASE_DIR, "youtube_cookies.txt")
STATE_FILE   = os.path.join(BASE_DIR, "data", "yt_seen.json")
LOCAL_PODCAST = os.path.join(BASE_DIR, "data", "podcasts.json")

def _secret(key):
    if key in os.environ:
        return os.environ[key]
    try:
        import tomllib
        p = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")
        with open(p, "rb") as f:
            return tomllib.load(f).get(key)
    except Exception:
        return None

GEMINI_KEY = _secret("GEMINI_API_KEY")
GSHEET_ID  = _secret("GSHEET_ID")

# ── 已看過的影片 ID ────────────────────────────────────────────────────────
def load_seen():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False)

# ── 頻道最新影片（flat 模式，不下載影片資訊）──────────────────────────────
def _get_channel_id(channel_url):
    """從頻道 handle URL 取得 channel_id"""
    r = requests.get(
        channel_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        timeout=15,
    )
    for pat in [r'"channelId":"(UC[^"]+)"', r'"externalId":"(UC[^"]+)"']:
        m = re.search(pat, r.text)
        if m:
            return m.group(1)
    return None

def get_latest_videos(channel_url, n=3):
    """用 YouTube RSS feed 取最新影片，不觸發 rate-limit"""
    import xml.etree.ElementTree as ET
    channel_id = _get_channel_id(channel_url)
    if not channel_id:
        return []
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    r = requests.get(rss_url, timeout=15)
    root = ET.fromstring(r.content)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt":   "http://www.youtube.com/xml/schemas/2015",
        "media":"http://search.yahoo.com/mrss/",
    }
    channel_name = root.findtext("atom:title", default=channel_url, namespaces=ns)
    videos = []
    for entry in root.findall("atom:entry", ns)[:n]:
        vid_id = entry.findtext("yt:videoId", namespaces=ns)
        title  = entry.findtext("atom:title", default="", namespaces=ns)
        if vid_id:
            videos.append({
                "id":      vid_id,
                "title":   title,
                "channel": channel_name,
                "url":     f"https://www.youtube.com/watch?v={vid_id}",
                "date":    str(datetime.date.today()),
            })
    return videos

# 短影音（YouTube Shorts）長度上限抓 90 秒當保守值，低於這個時長就跳過，
# 不耗用字幕抓取與 Gemini 額度。
SHORTS_MAX_DURATION = 90


def get_video_info(video_id):
    """抓影片 metadata（含時長），失敗回傳 None。"""
    ydl_opts = {
        "quiet": True,
        "cookiefile": COOKIES_FILE,
        "ignoreerrors": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False, process=False,
            )
    except Exception as e:
        print(f"  [!] 無法取得影片資訊: {e}")
        return None


def is_short(info):
    """用時長判斷是不是 YouTube Shorts（短影音）。"""
    duration = info.get("duration") if info else None
    return duration is not None and duration <= SHORTS_MAX_DURATION


# ── 字幕抓取（process=False 拿 URL，再手動 requests 下載）────────────────
def get_transcript(info):
    if not info:
        return None

    subs = info.get("subtitles", {})
    auto = info.get("automatic_captions", {})

    for lang in ["zh-TW", "zh-Hant", "zh-Hans", "zh-Hant-zh-TW", "zh-Hans-zh-TW", "zh-CN", "zh", "yue", "en"]:
        src = subs.get(lang) or auto.get(lang)
        if not src:
            continue
        for fmt in src:
            if fmt.get("ext") == "json3":
                try:
                    r = requests.get(fmt["url"], timeout=30)
                    data = r.json()
                    events = data.get("events", [])
                    text = " ".join(
                        "".join(s.get("utf8", "") for s in e.get("segs", []))
                        for e in events if "segs" in e
                    )
                    text = re.sub(r"\s+", " ", text).strip()
                    if text:
                        return text
                except Exception:
                    continue
    return None

# ── Gemini 整理 ─────────────────────────────────────────────────────────────
JSON_FMT = """{
  "bull": "看多標的（股票或板塊，逗號分隔）",
  "bear": "看空標的（股票或板塊，逗號分隔）",
  "view": "市場觀點（2-4句）",
  "trade": "操作建議（1-3句）",
  "notes": "其他重點"
}"""

def gemini_organize(transcript, title):
    if not GEMINI_KEY:
        print("  [!] 沒有 GEMINI_API_KEY，跳過整理")
        return None
    prompt = (
        f"以下是 YouTube 財經節目《{title}》的逐字稿，"
        "請整理投資觀點，用繁體中文，只回 JSON 不要其他文字：\n\n"
        + transcript[:12000]
        + f"\n\n格式：{JSON_FMT}"
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    r = requests.post(url, json=payload, timeout=60)
    for attempt in range(2):
        if r.status_code != 503:
            break
        print(f"  [!] Gemini 503 過載，{2**(attempt+1)}秒後重試...")
        time.sleep(2 ** (attempt + 1))
        r = requests.post(url, json=payload, timeout=60)
    if not r.ok:
        print(f"  [!] Gemini 錯誤 {r.status_code}: {r.text[:200]}")
        return None
    data = r.json()
    if "error" in data:
        print(f"  [!] Gemini 錯誤: {data['error']['message']}")
        return None
    parts = data["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts).strip()
    try:
        return extract_json_obj(text)
    except Exception as e:
        print(f"  [!] JSON 解析失敗: {e} | 原始回應: {text[:300]}")
        return None

# ── Google Sheets 寫入 ──────────────────────────────────────────────────────
def save_to_gsheets(new_episodes):
    gcp_json = _secret("gcp_service_account")
    if not GSHEET_ID or not gcp_json:
        return
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        if isinstance(gcp_json, str):
            gcp_json = json.loads(gcp_json)
        creds = Credentials.from_service_account_info(
            gcp_json,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(GSHEET_ID)
        try:
            ws = sh.worksheet("podcasts")
        except Exception:
            ws = sh.add_worksheet(title="podcasts", rows=10, cols=2)

        existing_raw = ws.acell("A1").value or "{}"
        existing_data = json.loads(existing_raw)
        # 支援 app 的 {"__channels__": [...], "episodes": [...]} 格式
        if isinstance(existing_data, list):
            channels = []
            existing_eps = existing_data
        elif isinstance(existing_data, dict):
            channels = existing_data.get("__channels__", [])
            existing_eps = existing_data.get("episodes", [])
        else:
            channels, existing_eps = [], []

        existing_yt_ids = {e.get("yt_id") for e in existing_eps if isinstance(e, dict)}
        added = [e for e in new_episodes if e.get("yt_id") not in existing_yt_ids]
        # 自動把新頻道名稱加入 __channels__
        for e in added:
            ch = e.get("podcast", "")
            if ch and ch not in channels:
                channels.append(ch)
        if added:
            merged_eps = added + existing_eps
            payload = {"__channels__": channels, "episodes": merged_eps}
            ws.update([[json.dumps(payload, ensure_ascii=False)]], "A1")
            print(f"  [OK] 已寫入 {len(added)} 集到 Google Sheets")
    except Exception as e:
        import traceback
        print(f"  [!] Google Sheets 寫入失敗: {e}")
        traceback.print_exc()

def save_local(new_episodes):
    os.makedirs(os.path.dirname(LOCAL_PODCAST), exist_ok=True)
    channels, existing = [], []
    if os.path.exists(LOCAL_PODCAST):
        with open(LOCAL_PODCAST, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list):
            existing = [e for e in raw if isinstance(e, dict)]
        elif isinstance(raw, dict):
            channels = raw.get("__channels__", [])
            existing = raw.get("episodes", [])
    existing_yt_ids = {e.get("yt_id") for e in existing if isinstance(e, dict)}
    added = [e for e in new_episodes if e.get("yt_id") not in existing_yt_ids]
    for e in added:
        ch = e.get("podcast", "")
        if ch and ch not in channels:
            channels.append(ch)
    if added:
        merged_eps = added + existing
        payload = {"__channels__": channels, "episodes": merged_eps}
        with open(LOCAL_PODCAST, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

# ── 主流程 ─────────────────────────────────────────────────────────────────
# 每個頻道只要抓到「最新一支長影片」就停手，不繼續往下處理同一頻道更舊的影片，
# 即使 RSS 裡還有其他新項目（通常是短影音或更早的影片）。n_per_channel 只是
# RSS 抓幾筆候選來篩，不是真的會全部整理。
def main(n_per_channel=5, max_channels=None):
    seen = load_seen()
    new_episodes = []

    channels = CHANNELS[:max_channels] if max_channels else CHANNELS
    for ch_url in channels:
        print(f"\n檢查頻道: {ch_url}")
        try:
            videos = get_latest_videos(ch_url, n=n_per_channel)
        except Exception as e:
            print(f"  [!] 抓頻道失敗: {e}")
            continue

        for v in videos:
            vid_id = v["id"]
            if vid_id in seen:
                print(f"  已處理: {v['title'][:50]}")
                continue

            print(f"  新影片: {v['title'][:60]}")
            import time; time.sleep(3)  # 避免 rate-limit
            info = get_video_info(vid_id)
            seen.add(vid_id)

            if is_short(info):
                print(f"  [-] 短影音（{info.get('duration')}秒），略過")
                continue

            # 找到最新的長影片了，這個頻道這次就只處理這一支
            transcript = get_transcript(info)

            if not transcript:
                print("  [!] 沒有字幕，略過整理")
                ep = {
                    "id":      str(uuid.uuid4())[:8],
                    "yt_id":   vid_id,
                    "podcast": v["channel"],
                    "title":   v["title"],
                    "date":    v["date"],
                    "link":    v["url"],
                    "tags":    ["auto", "no-transcript"],
                    "bull": "", "bear": "", "view": "", "trade": "", "notes": "（無字幕）",
                }
            else:
                print(f"  字幕長度: {len(transcript)} 字")
                ai = gemini_organize(transcript, v["title"])
                ep = {
                    "id":      str(uuid.uuid4())[:8],
                    "yt_id":   vid_id,
                    "podcast": v["channel"],
                    "title":   v["title"],
                    "date":    v["date"],
                    "link":    v["url"],
                    "tags":    ["auto"] if ai else ["auto", "ai-failed"],
                    "bull":    ai.get("bull", "") if ai else "",
                    "bear":    ai.get("bear", "") if ai else "",
                    "view":    ai.get("view", "") if ai else "",
                    "trade":   ai.get("trade", "") if ai else "",
                    # AI 整理失敗時把逐字稿存進 notes，這樣之後在網頁用
                    # 「編輯此筆記」→「AI 重新整理」還有內容可以重新分析，
                    # 不會變成完全空白、無從補救。
                    "notes":   ai.get("notes", "") if ai else f"（AI 整理失敗，以下為原始逐字稿，可在網頁編輯此筆記重新整理）\n\n{transcript[:3000]}",
                }
                if ai:
                    print("  [OK] 整理完成")
                else:
                    print("  [!] AI 整理失敗（已存逐字稿，可之後重試）")

            new_episodes.append(ep)
            break  # 這個頻道已經抓到最新長影片，這次不再處理更舊的項目

    if new_episodes:
        print(f"\n共新增 {len(new_episodes)} 集，儲存中...")
        save_local(new_episodes)
        save_to_gsheets(new_episodes)
    else:
        print("\n沒有新影片。")

    save_seen(seen)
    print("完成。")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5,
                         help="每個頻道從 RSS 抓幾筆候選來篩選短影音，實際每頻道只會整理最新一支長影片")
    parser.add_argument("--channels", type=int, default=None, help="只測試前幾個頻道")
    args = parser.parse_args()
    main(n_per_channel=args.n, max_channels=args.channels)
