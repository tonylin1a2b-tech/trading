"""Google Sheets 讀寫 helper
每個資料集存在獨立的 worksheet tab，JSON 字串存在 A1 儲存格。
若 st.secrets 沒有 gcp_service_account，自動 fallback 到本機 JSON 檔。
讀取結果快取在 session_state，同一個 session 只打一次 API。
"""
import json
import os
import streamlit as st

_gc = None
_sh = None
_ws_cache = {}
_CACHE_KEY = "__gsheets_cache__"

def _enabled() -> bool:
    try:
        return "gcp_service_account" in st.secrets and "GSHEET_ID" in st.secrets
    except Exception:
        return False

def _get_sheet():
    global _gc, _sh
    if _sh is not None:
        return _sh
    import gspread
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    _gc = gspread.authorize(creds)
    _sh = _gc.open_by_key(st.secrets["GSHEET_ID"])
    return _sh

def _get_or_create_ws(name: str):
    if name in _ws_cache:
        return _ws_cache[name]
    sh = _get_sheet()
    try:
        ws = sh.worksheet(name)
    except Exception:
        ws = sh.add_worksheet(title=name, rows=10, cols=2)
    _ws_cache[name] = ws
    return ws

def _session_cache() -> dict:
    if _CACHE_KEY not in st.session_state:
        st.session_state[_CACHE_KEY] = {}
    return st.session_state[_CACHE_KEY]

def load(name: str, local_path: str, default):
    """讀資料：session 內只打一次 Google Sheets API"""
    cache = _session_cache()
    if name in cache:
        return cache[name]

    data = None
    if _enabled():
        try:
            ws = _get_or_create_ws(name)
            val = ws.acell("A1").value
            if val:
                data = json.loads(val)
        except Exception:
            pass

    if data is None and local_path and os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    if data is None:
        data = default

    cache[name] = data
    return data

def save(name: str, local_path: str, data):
    """寫資料：更新 session cache + Google Sheets + 本機檔案"""
    # 更新 session cache
    _session_cache()[name] = data

    payload = json.dumps(data, ensure_ascii=False)
    if _enabled():
        try:
            ws = _get_or_create_ws(name)
            ws.update("A1", [[payload]])
        except Exception as e:
            st.warning(f"Google Sheets 寫入失敗：{e}")

    if local_path:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
