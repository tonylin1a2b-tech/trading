"""Google Sheets 讀寫 helper
每個資料集存在獨立的 worksheet tab，JSON 字串存在 A1 儲存格。
若 st.secrets 沒有 gcp_service_account，自動 fallback 到本機 JSON 檔。
"""
import json
import os
import streamlit as st

_gc = None
_sh = None

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
    sh = _get_sheet()
    try:
        return sh.worksheet(name)
    except Exception:
        return sh.add_worksheet(title=name, rows=10, cols=2)

def load(name: str, local_path: str, default):
    """讀資料：優先 Google Sheets，否則讀本機檔案，都沒有回傳 default"""
    if _enabled():
        try:
            ws = _get_or_create_ws(name)
            val = ws.acell("A1").value
            if val:
                return json.loads(val)
        except Exception:
            pass
    # fallback: 本機檔案
    if local_path and os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save(name: str, local_path: str, data):
    """寫資料：同時寫 Google Sheets 和本機檔案"""
    payload = json.dumps(data, ensure_ascii=False)
    if _enabled():
        try:
            ws = _get_or_create_ws(name)
            ws.update("A1", [[payload]])
        except Exception as e:
            st.warning(f"Google Sheets 寫入失敗：{e}")
    # 同時寫本機（方便本地開發）
    if local_path:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
