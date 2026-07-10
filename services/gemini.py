# services/gemini.py — Gemini API 呼叫與 YouTube 字幕抓取

import json
import os
import re
import time

import requests


def gemini_post_with_retry(url: str, payload: dict, timeout: int = 60, max_retries: int = 3):
    """呼叫 Gemini API，遇到 503/429 自動重試"""
    last_resp = None
    for attempt in range(max_retries):
        r = requests.post(url, json=payload, timeout=timeout)
        if r.status_code not in (503, 429):
            return r
        last_resp = r
        if attempt < max_retries - 1:
            if r.status_code == 429:
                m = re.search(r"retry in ([\d.]+)s", r.text)
                wait = float(m.group(1)) + 2 if m else 15
            else:
                wait = 2 ** attempt
            time.sleep(wait)
    return last_resp


def extract_json_obj(text: str):
    """從 Gemini 回應中解析 JSON，容忍前後說明文字與 code fence"""
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


_YT_COOKIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "youtube_cookies.txt")


def get_youtube_transcript(video_id: str):
    """用 yt-dlp 抓字幕文字；抓不到回傳 None"""
    try:
        import yt_dlp
    except ImportError:
        return None
    ydl_opts = {"quiet": True, "ignoreerrors": True}
    if os.path.exists(_YT_COOKIES_FILE):
        ydl_opts["cookiefile"] = _YT_COOKIES_FILE
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False, process=False,
            )
    except Exception:
        return None
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
