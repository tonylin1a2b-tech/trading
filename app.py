# app.py — 台股交易系統入口

import streamlit as st

import utils.data_health as _dh
from utils.ui import inject_css

st.set_page_config(
    page_title="台股交易系統",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()

# ── 側邊欄導覽 ─────────────────────────────────────────────────────────────
_sb_title_col, _sb_theme_col = st.sidebar.columns([3, 1])
_sb_title_col.markdown("### 📊 台股交易系統")
_is_dark_now = st.session_state.get("theme", "light") == "dark"
_theme_icon  = "☀️" if _is_dark_now else "🌙"
if _sb_theme_col.button(_theme_icon, key="theme_toggle", help="切換日/夜間模式"):
    st.session_state["theme"] = "light" if _is_dark_now else "dark"
    st.rerun()
st.sidebar.divider()

_PAGES = [
    "🏠 選股系統",
    "🌍 總經儀表板",
    "📰 新聞監控",
    "📊 散戶指標",
    "📈 個股監控",
    "🌡️ 板塊熱力圖",
    "🔬 產業研究",
    "🎙️ Podcast 整理",
    "🤖 AI 問答",
]

page = st.sidebar.radio("選擇頁面", _PAGES, key="nav_page")
_dh.render_sidebar()

# ── 頁面路由 ───────────────────────────────────────────────────────────────
if page == "🏠 選股系統":
    from views.home import render
    render()

elif page == "🌍 總經儀表板":
    # TODO: from views.macro import render; render()
    st.info("🚧 總經儀表板 — 正在搬移中，請暫時使用 main.py")

elif page == "📰 新聞監控":
    # TODO: from views.news import render; render()
    st.info("🚧 新聞監控 — 正在搬移中，請暫時使用 main.py")

elif page == "📊 散戶指標":
    # TODO: from views.sentiment import render; render()
    st.info("🚧 散戶指標 — 正在搬移中，請暫時使用 main.py")

elif page == "📈 個股監控":
    # TODO: from views.monitor import render; render()
    st.info("🚧 個股監控 — 正在搬移中，請暫時使用 main.py")

elif page == "🌡️ 板塊熱力圖":
    # TODO: from views.heatmap import render; render()
    st.info("🚧 板塊熱力圖 — 正在搬移中，請暫時使用 main.py")

elif page == "🔬 產業研究":
    # TODO: from views.sector import render; render()
    st.info("🚧 產業研究 — 正在搬移中，請暫時使用 main.py")

elif page == "🎙️ Podcast 整理":
    # TODO: from views.podcast import render; render()
    st.info("🚧 Podcast 整理 — 正在搬移中，請暫時使用 main.py")

elif page == "🤖 AI 問答":
    # TODO: from views.ai_qa import render; render()
    st.info("🚧 AI 問答 — 正在搬移中，請暫時使用 main.py")
