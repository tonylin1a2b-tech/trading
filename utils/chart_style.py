# utils/chart_style.py — 圖表樣式工具（顏色、Treemap、差異長條圖）

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import COLOR_UP, COLOR_DOWN

# ── Treemap 色階（綠跌/紅漲，台股慣例）─────────────────────
TREEMAP_CSCALE = [
    [0.00, "#1b5e20"],
    [0.25, "#43a047"],
    [0.42, "#a5d6a7"],
    [0.50, "#eceff1"],
    [0.58, "#ef9a9a"],
    [0.75, "#e53935"],
    [1.00, "#b71c1c"],
]


def diff_color_style(v) -> str:
    """DataFrame.style.map 用：數值上色（正值紅，負值綠）"""
    if not isinstance(v, (int, float)) or pd.isna(v):
        return ""
    color = COLOR_UP if v > 0 else COLOR_DOWN
    return f"color:{color};font-weight:600"


def direction_style(val: str) -> str:
    """Fed 方向欄上色"""
    s = str(val)
    if "降息" in s:
        return f"color:{COLOR_DOWN};font-weight:600"
    if "升息" in s:
        return f"color:{COLOR_UP};font-weight:600"
    return "color:#888"


def render_diff_bar_chart(
    df, date_col, cols_and_names, title, yaxis_title,
    color_by_sign=False, barmode=None,
):
    """「較前一日變化量」長條圖。cols_and_names = [(欄位名, 圖例名), ...]"""
    diff_data = {name: df[col].diff() for col, name in cols_and_names}
    df_diff = pd.DataFrame(diff_data)
    df_diff["日期"] = df[date_col].values
    df_diff = df_diff.dropna(subset=[cols_and_names[0][1]])
    if df_diff.empty:
        return

    fig = go.Figure()
    for _, name in cols_and_names:
        kwargs: dict = {}
        if color_by_sign:
            kwargs["marker_color"] = [
                "crimson" if v < 0 else "seagreen" for v in df_diff[name]
            ]
        fig.add_trace(go.Bar(x=df_diff["日期"], y=df_diff[name], name=name, **kwargs))
    fig.add_hline(y=0, line_dash="dot", line_color="gray")

    layout: dict = dict(
        title=title, xaxis_title="日期", yaxis_title=yaxis_title,
        hovermode="x unified",
    )
    if barmode:
        layout["barmode"] = barmode
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)


def build_treemap_fig(labels, parents, values, colors, customs, title, height=580):
    """建立 Treemap Figure（板塊熱力圖用）"""
    fig = go.Figure(go.Treemap(
        labels=labels, parents=parents, values=values, customdata=customs,
        marker=dict(
            colors=colors, colorscale=TREEMAP_CSCALE, cmid=0, cmin=-5, cmax=5,
            showscale=True,
            colorbar=dict(
                title=dict(text="漲跌%", font=dict(size=11)),
                thickness=12, len=0.65,
                tickvals=[-5, -3, -1, 0, 1, 3, 5],
                ticktext=["-5% 跌", "-3%", "-1%", "0", "+1%", "+3%", "+5% 漲"],
                tickfont=dict(size=10),
            ),
            pad=dict(t=4, l=2, r=2, b=2),
            line=dict(width=1.5, color="#ffffff"),
        ),
        texttemplate=(
            "<b>%{label}</b>"
            "<br>%{customdata[0]}"
            "<br><b>%{customdata[1]}</b>"
        ),
        textposition="middle center",
        textfont=dict(size=13, family="Arial, sans-serif", color="#ffffff"),
        hovertemplate=(
            "<b>%{label}</b><br>現價：%{customdata[0]}"
            "<br>漲跌：%{customdata[1]}<extra></extra>"
        ),
        tiling=dict(packing="squarify", pad=3),
    ))
    fig.update_layout(
        margin=dict(t=50, l=5, r=80, b=5), height=height,
        paper_bgcolor="#0e1117", font=dict(color="#fafafa"),
        title=dict(text=f"<b>{title}</b>", font=dict(size=17, color="#fafafa"), x=0.01),
    )
    return fig
