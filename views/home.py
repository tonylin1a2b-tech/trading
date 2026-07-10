# views/home.py — 🏠 選股系統

import concurrent.futures as _cf
import datetime
import io
import json
import os
import time as _time

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_lightweight_charts import renderLightweightCharts
from FinMind.data import DataLoader

from services.market import fetch_stock_kline
from signals import add_bbreak_signals, bbreak_to_chart_markers
from utils.http import safe_request
from utils.ui import page_banner


def render():
    page_banner("SCREENER", "選股系統", "動能選股 · 破底翻掃描")
    _tab_screen, _tab_bbreak = st.tabs(["📊 動能選股", "🔍 破底翻掃描"])

    with _tab_screen:
        st_autorefresh(interval=20 * 60 * 1000, key="stock_refresh")
        st.divider()

        _MA_OPTS = [5, 10, 20, 60]
        _EXTRA_OPTIONS = [
            "📈 營收創新高（近12個月）",
            "📊 成交量放大（>1.5倍5日均量）",
            "🔀 5日均線 > 20日均線（短多排列）",
        ]
        st.session_state.setdefault("screen_top_n", 100)
        st.session_state.setdefault("screen_ma_idx", 2)
        st.session_state.setdefault("screen_range_pct", 3.0)
        st.session_state.setdefault("screen_extra", [])

        st.subheader("🔧 選股條件設定")
        with st.form("screener_form"):
            _fc1, _fc2 = st.columns(2)
            with _fc1:
                top_n = st.number_input(
                    "成交值排名前 N 檔", min_value=20, max_value=300,
                    value=int(st.session_state["screen_top_n"]), step=10)
                ma_period = st.selectbox(
                    "均線天數", _MA_OPTS,
                    index=st.session_state["screen_ma_idx"])
            with _fc2:
                range_pct = st.slider(
                    "距均線範圍（±%）", min_value=0.5, max_value=10.0,
                    value=float(st.session_state["screen_range_pct"]), step=0.5)
            extra_filters = st.multiselect(
                "額外篩選條件（可複選）", _EXTRA_OPTIONS,
                default=st.session_state["screen_extra"])
            if _EXTRA_OPTIONS[0] in extra_filters:
                st.caption("⚠️ 「營收創新高」需對每檔額外查詢月營收，掃描時間會明顯變長")
            run_screen = st.form_submit_button("🔍 開始選股", type="primary", use_container_width=True)

        if run_screen:
            st.session_state["screen_top_n"]     = top_n
            st.session_state["screen_ma_idx"]    = _MA_OPTS.index(ma_period)
            st.session_state["screen_range_pct"] = range_pct
            st.session_state["screen_extra"]     = extra_filters

        ext_flags = {
            "rev_high":   _EXTRA_OPTIONS[0] in extra_filters,
            "vol_expand": _EXTRA_OPTIONS[1] in extra_filters,
            "golden":     _EXTRA_OPTIONS[2] in extra_filters,
        }

        CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cache")
        os.makedirs(CACHE_DIR, exist_ok=True)
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        ext_key   = f"r{int(ext_flags['rev_high'])}v{int(ext_flags['vol_expand'])}g{int(ext_flags['golden'])}"
        cache_file = os.path.join(CACHE_DIR, f"screener_{today_str}_top{top_n}_ma{ma_period}_pm{range_pct}_{ext_key}.csv")

        DISPLAY_COLS = list(dict.fromkeys(
            ["證券代號", "證券名稱", "成交金額(億)", "收盤價",
             f"{ma_period}日均線", "距均線(%)", "5日均線", "20日均線",
             "成交量(張)", "5日均量(張)"]
        ))
        if ext_flags["rev_high"]:
            DISPLAY_COLS.append("近12月營收創高")

        TV_LINK_CONFIG = {"證券代號": st.column_config.LinkColumn(
            "證券代號", display_text=r"symbol=TWSE:(\d+)")}

        def with_tradingview_link(df):
            df = df.copy()
            df["證券代號"] = "https://www.tradingview.com/chart/?symbol=TWSE:" + df["證券代號"].astype(str)
            return df

        def _show_result(result: pd.DataFrame):
            disp = result[[c for c in DISPLAY_COLS if c in result.columns]].copy()
            disp = disp.rename(columns={"收盤價_x": "收盤價"})

            def _diff_color(v):
                if not isinstance(v, (int, float)) or pd.isna(v):
                    return ""
                return "color:#c0392b;font-weight:600" if v > 0 else "color:#27ae60;font-weight:600"

            disp_tv = with_tradingview_link(disp)
            styled  = disp_tv.style.map(_diff_color, subset=["距均線(%)"] if "距均線(%)" in disp_tv.columns else [])

            st.dataframe(styled, column_config=TV_LINK_CONFIG,
                         use_container_width=True,
                         height=min(600, 35 * len(disp) + 38))

            _csv = disp.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                "⬇️ 下載 CSV", _csv,
                file_name=f"screener_{today_str}_ma{ma_period}.csv",
                mime="text/csv", key="dl_screener_csv")

            if not result.empty and "證券代號" in result.columns:
                st.markdown("---")
                _stock_opts = result.apply(
                    lambda r: f"{r['證券代號']}　{r.get('證券名稱', '')}", axis=1
                ).tolist()
                _gc1, _gc2 = st.columns([3, 1])
                _sel = _gc1.selectbox(
                    "跳到個股監控", _stock_opts,
                    key="screen_goto_sel", label_visibility="collapsed")
                if _gc2.button("📈 個股監控", key="screen_goto_btn"):
                    _sid = str(_sel).split()[0]
                    st.session_state["monitor_goto_id"] = _sid
                    st.session_state["nav_page"] = "📈 個股監控"
                    st.rerun()

        if os.path.exists(cache_file):
            st.success(f"📌 今天（{today_str}）已用相同條件掃描過，直接讀取鎖定結果，不重新呼叫 API")
            result = pd.read_csv(cache_file)
            result.index = range(1, len(result) + 1)
            st.subheader(f"資料日期：{today_str}　符合條件：{len(result)} 檔")
            _show_result(result)

        elif run_screen:
            api = DataLoader()
            api.login_by_token(api_token=st.secrets["FINMIND_TOKEN"])

            with st.spinner(f"正在抓取成交值前 {top_n} 名..."):
                stock_info = api.taiwan_stock_info()
                stock_info = stock_info[~stock_info["industry_category"].str.contains("ETF|基金", na=False)]
                stock_info = stock_info[stock_info["stock_id"].str.match(r"^\d{4}$")]
                valid_stocks = set(stock_info["stock_id"].tolist())

                url  = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json"
                res  = safe_request(url, headers={"User-Agent": "Mozilla/5.0"})
                if res is None:
                    st.error("TWSE 資料暫時無法取得，請稍後再試")
                    st.stop()
                ctype = res.headers.get("content-type", "")
                try:
                    if "json" in ctype:
                        data = res.json()
                        df   = pd.DataFrame(data["data"], columns=data["fields"])
                    else:
                        df   = pd.read_csv(io.StringIO(res.text), dtype=str, on_bad_lines="skip")
                except Exception as e:
                    st.error(f"TWSE 資料解析失敗：{e}，請稍後再試")
                    st.stop()
                df["成交金額"] = df["成交金額"].str.replace(",", "").astype(float)
                df["成交金額(億)"] = (df["成交金額"] / 1e8).round(2)
                df = df[df["證券代號"].isin(valid_stocks)]
                topN      = df.sort_values("成交金額", ascending=False).head(top_n).reset_index(drop=True)
                stock_ids = topN["證券代號"].tolist()

            end_date       = datetime.date.today().strftime("%Y-%m-%d")
            lookback_days  = max(ma_period, 20) * 3 + 30
            start_date     = (datetime.date.today() - datetime.timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            rev_start_date = (datetime.date.today() - datetime.timedelta(days=400)).strftime("%Y-%m-%d")
            _fm_token      = st.secrets["FINMIND_TOKEN"]

            def _screen_one(sid):
                try:
                    _api = DataLoader()
                    _api.login_by_token(api_token=_fm_token)
                    price = _api.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=end_date)
                    if len(price) < max(ma_period, 20, 6):
                        return None
                    price  = price.sort_values("date")
                    ma     = price["close"].iloc[-ma_period:].mean()
                    close  = price["close"].iloc[-1]
                    diff_pct = (close - ma) / ma * 100
                    if not (-range_pct <= diff_pct <= range_pct):
                        return None
                    ma5  = price["close"].iloc[-5:].mean()
                    ma20 = price["close"].iloc[-20:].mean()
                    if ext_flags["golden"] and not (ma5 > ma20):
                        return None
                    vol_ma5    = price["Trading_Volume"].iloc[-6:-1].mean()
                    latest_vol = price["Trading_Volume"].iloc[-1]
                    if ext_flags["vol_expand"] and not (vol_ma5 > 0 and latest_vol > 1.5 * vol_ma5):
                        return None
                    row = {
                        "證券代號":          sid,
                        f"{ma_period}日均線": round(ma, 2),
                        "收盤價":            close,
                        "距均線(%)":         round(diff_pct, 2),
                        "5日均線":           round(ma5, 2),
                        "20日均線":          round(ma20, 2),
                        "成交量(張)":        int(latest_vol / 1000),
                        "5日均量(張)":       int(vol_ma5 / 1000),
                    }
                    if ext_flags["rev_high"]:
                        rev = _api.taiwan_stock_month_revenue(stock_id=sid, start_date=rev_start_date, end_date=end_date)
                        if len(rev) < 2:
                            return None
                        rev = rev.sort_values("date")
                        if rev["revenue"].iloc[-1] < rev["revenue"].max():
                            return None
                        row["近12月營收創高"] = "✅"
                    return row
                except Exception:
                    return None

            _total       = len(stock_ids)
            _result_list = []
            _prog = st.progress(0, text=f"掃描中... 0 / {_total} 檔")
            with _cf.ThreadPoolExecutor(max_workers=5) as _ex2:
                _futures = {_ex2.submit(_screen_one, sid): sid for sid in stock_ids}
                for _i, _fut in enumerate(_cf.as_completed(_futures), 1):
                    r = _fut.result()
                    if r is not None:
                        _result_list.append(r)
                    _prog.progress(_i / _total, text=f"掃描中... {_i} / {_total} 檔")
            _prog.empty()

            if _result_list:
                result = topN.merge(pd.DataFrame(_result_list), on="證券代號", how="inner")
                result = result.sort_values("距均線(%)", key=abs).reset_index(drop=True)
            else:
                result = pd.DataFrame(columns=DISPLAY_COLS)

            result.to_csv(cache_file, index=False, encoding="utf-8-sig")
            st.success("✅ 選股結果已鎖定，今天內重新整理將直接讀取，不再消耗 API 額度")
            result.index = range(1, len(result) + 1)
            st.subheader(f"資料日期：{today_str}　符合條件：{len(result)} 檔")
            _show_result(result)

        else:
            st.info("👆 設定好選股條件後，點擊「開始選股」執行掃描")

    with _tab_bbreak:
        st.caption("掃描自選清單中出現「布林通道破底翻」訊號的個股（必要條件：最低價跌破布林下軌 + 長下影線 ≥ 50%）")

        _DATA_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
        _SECTOR_LOCAL = os.path.join(_DATA_DIR, "sector_config.json")
        if os.path.exists(_SECTOR_LOCAL):
            with open(_SECTOR_LOCAL, encoding="utf-8") as _f:
                _sec_cfg_scan = json.load(_f)
        else:
            _sec_cfg_scan = {}

        def _flatten_tickers(cfg):
            result = {}
            for mkt_key, mkt_val in cfg.items():
                if not isinstance(mkt_val, dict):
                    continue
                if "台股" not in mkt_key:
                    continue
                for sec_val in mkt_val.values():
                    if isinstance(sec_val, dict):
                        result.update(sec_val)
            return result

        _all_stocks = _flatten_tickers(_sec_cfg_scan)

        with st.expander("➕ 額外加入掃描清單", expanded=False):
            _extra_raw = st.text_area("每行輸入一個股票代號（加 .TW 或 .TWO 後綴）", height=100,
                                       placeholder="2330.TW\n2454.TW", key="scan_extra")
            for _line in _extra_raw.strip().splitlines():
                _tk = _line.strip()
                if _tk and _tk not in _all_stocks.values():
                    _all_stocks[_tk] = _tk

        st.write(f"掃描範圍：**{len(_all_stocks)}** 支台股（來自個股監控自選清單）")

        st.markdown("**必要條件**")
        _col_bb, _col_sh = st.columns(2)
        _use_bb     = _col_bb.checkbox("跌破布林下軌", value=True, key="bb_ck")
        _use_shadow = _col_sh.checkbox("長下影線 ≥ 50%", value=True, key="sh_ck")

        st.markdown("**輔助條件**（預設關閉）")
        _col_r, _col_m, _col_v = st.columns(3)
        _use_rsi  = _col_r.checkbox("RSI < 35",     value=False, key="rsi_ck")
        _use_macd = _col_m.checkbox("MACD 背離",    value=False, key="macd_ck")
        _use_vol  = _col_v.checkbox("後5日放量確認", value=False, key="vol_ck")

        _scan_days = st.slider("掃描最近幾個交易日的訊號", min_value=1, max_value=10, value=1,
                                help="1 = 只看最新一根；設 3 就能抓近3天內出現過訊號的個股", key="scan_days_sl")

        if st.button("🔍 開始掃描", type="primary", key="scan_btn"):
            _cfg_key = (_use_bb, _use_shadow, _use_rsi, _use_macd, _use_vol)

            def _scan_one(name, ticker, cfg_key, scan_days):
                use_bb, use_shadow, use_rsi, use_macd, use_vol = cfg_key
                cfg_ov = {"use_rsi": use_rsi, "use_macd_div": use_macd, "use_vol_surge": use_vol}
                try:
                    import warnings as _w
                    _w.filterwarnings("ignore")
                    _base = ticker.split(".")[0]
                    df = fetch_stock_kline(_base, interval="1d", range_="3mo")
                    if df.empty or len(df) < 20:
                        return None, None
                    df = add_bbreak_signals(df, cfg_ov)
                    window = df.tail(scan_days).copy()
                    window["_hit"] = True
                    if use_bb:     window["_hit"] = window["_hit"] & window["first_bb_break"]
                    if use_shadow: window["_hit"] = window["_hit"] & window["long_shadow"]
                    if use_rsi:    window["_hit"] = window["_hit"] & window["aux_rsi"]
                    if use_macd:   window["_hit"] = window["_hit"] & window["aux_macd_div"]
                    if use_vol:    window["_hit"] = window["_hit"] & window["aux_vol_surge"]
                    hit_rows = window[window["_hit"] == True]
                    last_all = df.iloc[-1]
                    summary = {
                        "名稱": name, "代號": ticker,
                        "最新日期": str(last_all["date"])[:10],
                        "bb_break": bool(last_all["first_bb_break"]),
                        "long_shadow": bool(last_all["long_shadow"]),
                        "shadow_ratio": float(last_all.get("shadow_ratio", 0) or 0),
                    }
                    if hit_rows.empty:
                        return None, summary
                    last = hit_rows.iloc[-1]
                    result = {
                        "名稱":       name,
                        "代號":       ticker,
                        "日期":       str(last["date"])[:10],
                        "收盤":       round(float(last["close"]), 2),
                        "最低":       round(float(last["low"]), 2),
                        "布林下軌":   round(float(last["bb_lower"]), 2),
                        "下影線比例": f"{last['shadow_ratio']:.0%}",
                        "aux_rsi":  bool(last.get("aux_rsi", False)),
                        "aux_macd": bool(last.get("aux_macd_div", False)),
                        "aux_vol":  bool(last.get("aux_vol_surge", False)),
                    }
                    return result, summary
                except Exception:
                    return None, None

            _results, _summaries = [], []
            _prog  = st.progress(0, text="掃描中...")
            _total = len(_all_stocks)
            _t0    = _time.perf_counter()
            with _cf.ThreadPoolExecutor(max_workers=12) as _ex:
                _futures = {_ex.submit(_scan_one, n, t, _cfg_key, _scan_days): (n, t)
                            for n, t in _all_stocks.items()}
                for _i, _fut in enumerate(_cf.as_completed(_futures)):
                    _res, _summ = _fut.result()
                    if _res:  _results.append(_res)
                    if _summ: _summaries.append(_summ)
                    _prog.progress((_i + 1) / _total, text=f"掃描中... {_i+1}/{_total}")
            _prog.empty()
            _scan_elapsed = _time.perf_counter() - _t0

            _n_bb   = sum(1 for s in _summaries if s["bb_break"])
            _n_shad = sum(1 for s in _summaries if s["long_shadow"])
            st.markdown(f"掃描 **{len(_summaries)}** 支｜跌破布林：**{_n_bb}** 支｜長下影線：**{_n_shad}** 支｜兩者同時：**{len(_results)}** 支　⏱ {_scan_elapsed:.1f}s")

            _near = [s for s in _summaries if (s["bb_break"] or s["long_shadow"])
                     and not (s["bb_break"] and s["long_shadow"])]
            if _near and not _results:
                with st.expander(f"接近訊號（只差一個條件）— {len(_near)} 支"):
                    st.dataframe(pd.DataFrame([{
                        "名稱": s["名稱"], "代號": s["代號"],
                        "跌破布林": "✅" if s["bb_break"] else "—",
                        "長下影線": "✅" if s["long_shadow"] else "—",
                        "下影線比例": f"{s['shadow_ratio']:.0%}",
                    } for s in _near]), use_container_width=True, hide_index=True)

            if _results:
                st.success(f"找到 **{len(_results)}** 支出現破底翻訊號的個股")
                _df_res  = pd.DataFrame(_results)
                _df_show = _df_res[["名稱","代號","日期","收盤","最低","布林下軌","下影線比例"]].copy()
                if _use_rsi:  _df_show["RSI<35"]   = _df_res["aux_rsi"].map(lambda v: "✅" if v else "—")
                if _use_macd: _df_show["MACD背離"] = _df_res["aux_macd"].map(lambda v: "✅" if v else "—")
                if _use_vol:  _df_show["後5日放量"] = _df_res["aux_vol"].map(lambda v: "✅" if v else "—")
                st.dataframe(_df_show, use_container_width=True, hide_index=True)

                st.markdown("**點選個股查看 K 線圖：**")
                _btn_cols = st.columns(min(len(_results), 6))
                for _ci, _row in enumerate(_results):
                    if _btn_cols[_ci % len(_btn_cols)].button(_row["名稱"], key=f"bb_goto_{_row['代號']}"):
                        _prev = st.session_state.get("bb_preview_ticker")
                        if _prev == _row["代號"]:
                            st.session_state.pop("bb_preview_ticker", None)
                        else:
                            st.session_state["bb_preview_ticker"] = _row["代號"]
                            st.session_state["bb_preview_name"]   = _row["名稱"]

                _preview_ticker = st.session_state.get("bb_preview_ticker")
                if _preview_ticker:
                    _preview_name = st.session_state.get("bb_preview_name", _preview_ticker)
                    st.markdown(f"**📈 {_preview_name}　`{_preview_ticker}`**")
                    with st.spinner("載入K線..."):
                        _pure = _preview_ticker.split(".")[0]
                        _df_p = fetch_stock_kline(_pure, interval="1d", range_="6mo")
                    if _df_p.empty:
                        st.warning("無法取得K棒資料")
                    else:
                        _df_p    = add_bbreak_signals(_df_p)
                        _times_p = _df_p["date"].dt.strftime("%Y-%m-%d").tolist()
                        _candles_p = [{"time": t, "open": float(o), "high": float(h), "low": float(l), "close": float(c)}
                                      for t, o, h, l, c in zip(_times_p, _df_p["open"], _df_p["high"], _df_p["low"], _df_p["close"])]
                        _sigs_p  = bbreak_to_chart_markers(_df_p, _times_p)
                        _bb_line_p = [{"time": t, "value": round(float(v), 2)}
                                      for t, v in zip(_times_p, _df_p["bb_lower"]) if pd.notna(v)]
                        _chart_opts_p = {
                            "layout": {"background": {"color": "#0e1117"}, "textColor": "#e0e0e0"},
                            "grid": {"vertLines": {"color": "#1e2329"}, "horzLines": {"color": "#1e2329"}},
                            "height": 340,
                        }
                        _series_p = [
                            {"type": "Candlestick", "data": _candles_p,
                             "options": {"upColor":"#26a69a","downColor":"#ef5350","borderUpColor":"#26a69a","borderDownColor":"#ef5350","wickUpColor":"#26a69a","wickDownColor":"#ef5350"},
                             "markers": _sigs_p},
                            {"type": "Line", "data": _bb_line_p,
                             "options": {"color": "#ff6d00", "lineWidth": 1, "lineStyle": 2, "priceLineVisible": False}},
                        ]
                        renderLightweightCharts([{"chart": _chart_opts_p, "series": _series_p}],
                                               key=f"bb_preview_{_preview_ticker}")
            else:
                st.info("掃描範圍內沒有符合條件的個股（可拉大掃描天數或擴充自選清單）")
