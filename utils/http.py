"""
utils/http.py — 統一的 HTTP 工具層

提供：
  safe_request()  帶重試 + 指數退避的通用 HTTP 請求
  yf_chart()      解析 Yahoo Finance v8 chart API，失敗回傳 None

測試斷網降級：把 FORCE_FAIL 設為 True，所有 safe_request 都會直接回 None，
可用來驗收每個頁面是否能優雅降級。
"""
import time
import requests
import urllib3

urllib3.disable_warnings()

# ── 斷網模擬開關（驗收用，正常運作保持 False） ─────────────────────────────
FORCE_FAIL: bool = False

_YF_HEADERS = {"User-Agent": "Mozilla/5.0"}
_DEFAULT_TIMEOUT = 10
_DEFAULT_RETRIES = 3


def safe_request(
    url: str,
    method: str = "get",
    retries: int = _DEFAULT_RETRIES,
    timeout: int = _DEFAULT_TIMEOUT,
    **kwargs,
) -> "requests.Response | None":
    """
    帶重試的 HTTP 請求。
    失敗（含 FORCE_FAIL 模式）一律回傳 None，呼叫端統一判斷。
    重試策略：第 1 次失敗等 1s，第 2 次等 2s（指數退避）。
    """
    if FORCE_FAIL:
        return None

    kwargs.setdefault("verify", False)
    kwargs.setdefault("timeout", timeout)

    for attempt in range(retries):
        try:
            resp = getattr(requests, method)(url, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def yf_chart(symbol: str, interval: str = "1d", range_: str = "3mo") -> "dict | None":
    """
    抓取 Yahoo Finance v8 chart API 並解析 JSON。
    成功回傳 result[0] dict（含 timestamp, indicators 等），失敗回傳 None。
    """
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval={interval}&range={range_}"
    )
    resp = safe_request(url, headers=_YF_HEADERS)
    if resp is None:
        return None
    try:
        data = resp.json()
        if data.get("chart", {}).get("error"):
            return None
        results = data.get("chart", {}).get("result") or []
        return results[0] if results else None
    except Exception:
        return None
