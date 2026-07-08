"""
utils/data_health.py — 資料源健康狀態追蹤

使用方式：
  import utils.data_health as dh

  # 在取得資料後記錄
  dh.record("Yahoo Finance", ok=True)   # 成功
  dh.record("台灣期交所",    ok=False)  # 失敗

  # 在 sidebar 顯示
  dh.render_sidebar()
"""
import datetime
import streamlit as st

_KEY = "_data_health"

SOURCES = ["Yahoo Finance", "台灣期交所", "台灣證交所", "FinMind"]

# 狀態判斷閾值（分鐘）
_WARN_MINUTES = 5
_FAIL_MINUTES = 30


def record(source: str, ok: bool) -> None:
    """記錄資料源的最新一次存取結果。"""
    if _KEY not in st.session_state:
        st.session_state[_KEY] = {}
    h = st.session_state[_KEY]
    now = datetime.datetime.now()
    if ok:
        h[f"{source}_last_ok"] = now
        h[f"{source}_last_fail"] = h.get(f"{source}_last_fail")  # 保留，但成功了
    else:
        h[f"{source}_last_fail"] = now


def render_sidebar() -> None:
    """在 sidebar 底部顯示各資料源的健康狀態點。"""
    h = st.session_state.get(_KEY, {})
    now = datetime.datetime.now()

    st.sidebar.markdown("---")
    st.sidebar.caption("**資料源狀態**")

    for src in SOURCES:
        last_ok   = h.get(f"{src}_last_ok")
        last_fail = h.get(f"{src}_last_fail")

        if last_ok is None and last_fail is None:
            dot, label = "⚪", "未查詢"
        elif last_ok is None:
            # 從未成功過
            dot, label = "🔴", "失效"
        else:
            mins_ok = int((now - last_ok).total_seconds() / 60)
            # 最後一次失敗比最後一次成功還新 → 失效
            if last_fail and last_fail > last_ok:
                dot, label = "🔴", "失效"
            elif mins_ok < _WARN_MINUTES:
                dot, label = "🟢", "正常"
            elif mins_ok < _FAIL_MINUTES:
                dot, label = "🟡", f"延遲 {mins_ok}m"
            else:
                dot, label = "🔴", f"逾時 {mins_ok}m"

        ts = last_ok.strftime("%H:%M") if last_ok else "—"
        st.sidebar.caption(f"{dot} {src}：{label}（{ts}）")
