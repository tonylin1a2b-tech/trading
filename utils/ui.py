# utils/ui.py — UI 共用工具：CSS 主題注入、page_banner

import streamlit as st

# ── CSS 變數（日/夜）──────────────────────────────────────
_LIGHT_VARS = """
  :root {
    --bg:        #f5f7fa;
    --surface:   #ffffff;
    --surface2:  #eef2f7;
    --border:    #dde3ec;
    --accent:    #1565c0;
    --accent-mid:#1e88e5;
    --accent-lt: #e3f0fd;
    --accent-dim:#0d47a1;
    --text:      #1a2332;
    --text-dim:  #5a6a7e;
    --up:        #0d7a4e;
    --down:      #c62828;
    --banner-bg: linear-gradient(135deg,#e8f0fe 0%,#dceeff 50%,#f0f6ff 100%);
    --banner-h1: var(--accent);
    --banner-tag-bg: var(--accent);
    --banner-tag-color: #fff;
    --compass-overall-bg: var(--accent-lt);
    --shadow: 0 1px 4px rgba(21,101,192,0.06);
  }
"""

_DARK_VARS = """
  :root {
    --bg:        #0a0e1a;
    --surface:   #111827;
    --surface2:  #1a2235;
    --border:    #1e2d45;
    --accent:    #3b82f6;
    --accent-mid:#60a5fa;
    --accent-lt: rgba(59,130,246,0.12);
    --accent-dim:#1d4ed8;
    --text:      #e2e8f0;
    --text-dim:  #94a3b8;
    --up:        #10b981;
    --down:      #ef4444;
    --banner-bg: linear-gradient(135deg,#111827 0%,#0f172a 60%,#0a0e1a 100%);
    --banner-h1: #ffffff;
    --banner-tag-bg: rgba(59,130,246,0.2);
    --banner-tag-color: #60a5fa;
    --compass-overall-bg: var(--surface2);
    --shadow: 0 1px 4px rgba(0,0,0,0.3);
  }
"""

_CSS_COMMON = """
<style>
  __VARS__

  .stApp { background: var(--bg) !important; color: var(--text); }
  .block-container { padding-top: 0 !important; padding-bottom: 4rem; max-width: 1400px; }

  h1, h2, h3 { font-weight: 700; color: var(--text) !important; letter-spacing: -0.01em; }
  p, li, .stMarkdown { color: var(--text-dim); }

  [data-testid="stSidebar"] { background: var(--surface) !important; border-right: 1px solid var(--border); }
  [data-testid="stSidebar"] * { color: var(--text) !important; }
  [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label {
    padding: 6px 10px; border-radius: 8px; margin-bottom: 2px; transition: background 0.12s;
  }
  [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:hover { background: var(--accent-lt); }
  [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] div:has(input[type="radio"]) > div:first-child {
    background-color: var(--surface2) !important; border-color: var(--border) !important;
  }
  [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] div:has(input[type="radio"]:checked) > div:first-child {
    background-color: var(--accent) !important; border-color: var(--accent) !important;
  }
  [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label p { font-size: 0.92rem; font-weight: 500; }

  div[data-testid="stMetric"] {
    background: var(--surface) !important; border: 1px solid var(--border);
    border-radius: 12px; padding: 1.2rem 1.4rem; box-shadow: var(--shadow);
  }
  [data-testid="stMetricValue"] { font-size: 2rem !important; color: var(--accent) !important; font-weight: 700 !important; }
  [data-testid="stMetricLabel"] { color: var(--text-dim) !important; font-size: 0.82rem !important; font-weight: 500 !important; }
  [data-testid="stMetricDelta"] { font-size: 0.85rem !important; }

  div[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--surface) !important; border: 1px solid var(--border) !important;
    border-radius: 12px; box-shadow: var(--shadow);
  }

  .stButton > button {
    background: var(--surface) !important; border: 1px solid var(--border) !important;
    color: var(--text) !important; border-radius: 8px; font-weight: 500; transition: all 0.15s;
  }
  .stButton > button p { color: inherit !important; }
  .stButton > button:hover { border-color: var(--accent) !important; color: var(--accent) !important; background: var(--accent-lt) !important; }
  .stButton > button[kind="primary"] { background: var(--accent) !important; border-color: var(--accent) !important; color: #fff !important; }
  .stButton > button[kind="primary"]:hover { background: var(--accent-dim) !important; color: #fff !important; }

  .stTextInput input, .stTextArea textarea, div[data-baseweb="select"] > div, .stNumberInput input {
    background: var(--surface2) !important; border-color: var(--border) !important;
    color: var(--text) !important; border-radius: 8px;
  }
  div[data-baseweb="select"] span { color: var(--text) !important; }

  button[data-baseweb="tab"] { color: var(--text-dim) !important; background: transparent !important; font-weight: 500; }
  button[data-baseweb="tab"][aria-selected="true"] { color: var(--accent) !important; border-bottom: 2px solid var(--accent) !important; }
  div[data-testid="stTabs"] > div:first-child { border-bottom: 1px solid var(--border); }

  details { border: 1px solid var(--border) !important; border-radius: 10px; background: var(--surface) !important; }
  summary { color: var(--text) !important; }

  hr { border-color: var(--border) !important; }
  [data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
  .stAlert { border-radius: 10px; background: var(--surface) !important; }

  .page-banner {
    background: var(--banner-bg);
    border-bottom: 3px solid var(--accent);
    padding: 2rem 2rem 1.8rem;
    margin: 0.5rem -1rem 2rem -1rem;
    position: relative; overflow: hidden;
  }
  .page-banner::after {
    content: ""; position: absolute; right: -40px; top: -40px;
    width: 220px; height: 220px; border-radius: 50%;
    background: rgba(59,130,246,0.07); pointer-events: none;
  }
  .page-banner .banner-tag {
    display: inline-block; background: var(--banner-tag-bg); color: var(--banner-tag-color);
    border-radius: 4px; padding: 2px 10px; font-size: 0.72rem; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 0.8rem;
  }
  .page-banner h1 {
    font-size: 2rem !important; font-weight: 800 !important;
    color: var(--banner-h1) !important; margin: 0 0 0.4rem 0 !important; border: none !important;
  }
  .page-banner p { color: var(--text-dim); margin: 0; font-size: 0.92rem; }

  .compass-card {
    background: var(--surface) !important; border: 1px solid var(--border) !important;
    border-radius: 10px; padding: 0.8rem 1rem; margin-bottom: 0.5rem; box-shadow: var(--shadow);
  }
  .compass-card .label { color: var(--text-dim) !important; font-size: 0.8rem; margin-bottom: 3px; }
  .compass-card .value { color: var(--text) !important; font-weight: 600; font-size: 1rem; }
  .compass-overall {
    background: var(--compass-overall-bg) !important; border: 1px solid var(--border) !important;
    border-left: 4px solid var(--accent) !important; border-radius: 12px;
    padding: 1rem 1.2rem; margin-bottom: 1rem; text-align: center;
    font-size: 1.25rem; font-weight: 700; color: var(--accent) !important;
  }
</style>
"""


def inject_css() -> None:
    """依 session_state['theme'] 注入 CSS 主題變數"""
    if "theme" not in st.session_state:
        st.session_state["theme"] = "light"
    _vars = _DARK_VARS if st.session_state["theme"] == "dark" else _LIGHT_VARS
    st.markdown(_CSS_COMMON.replace("__VARS__", _vars), unsafe_allow_html=True)


def page_banner(tag: str, title: str, subtitle: str = "") -> None:
    """全寬頁首 Banner"""
    sub_html = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(f"""
<div class="page-banner">
  <div class="banner-tag">{tag}</div>
  <h1>{title}</h1>
  {sub_html}
</div>""", unsafe_allow_html=True)
