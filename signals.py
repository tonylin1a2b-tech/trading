"""
破底翻（布林通道版）訊號偵測模組
輸入：fetch_stock_kline 回傳的 df（欄位：date, open, high, low, close, volume）
輸出：同一 df，新增下列欄位
  - bb_break      : 布林下軌跌破（必要條件1）
  - long_shadow   : 長下影線（必要條件2）
  - signal        : 布林通道破底翻主訊號（必要條件1 & 2 同時成立）
  - aux_rsi       : 輔助條件3 - RSI 低於門檻
  - aux_macd_div  : 輔助條件4 - MACD 背離
  - aux_vol_surge : 輔助條件5 - 訊號後 N 日內出現量能放大（回測用）
"""
import pandas as pd
import numpy as np

# ── 所有可調參數集中在這裡 ────────────────────────────────────────────────
CFG = {
    # 必要條件 1：布林通道
    "bb_period": 20,          # 布林通道計算天數
    "bb_std":    2.0,         # 標準差倍數

    # 必要條件 2：長下影線
    "shadow_ratio": 0.50,     # 下影線 / 全天區間 ≥ 此值

    # 輔助條件 3：RSI 超賣（預設關閉）
    "use_rsi":    False,
    "rsi_period": 14,
    "rsi_thresh": 35,

    # 輔助條件 4：MACD 背離（預設關閉）
    "use_macd_div":   False,
    "macd_fast":      12,
    "macd_slow":      26,
    "macd_signal":    9,
    "div_lookback":   20,     # 找近期新低的回溯天數

    # 輔助條件 5：訊號後量能確認（預設關閉，回測用）
    "use_vol_surge":  False,
    "vol_ma_period":  20,     # 均量天數
    "vol_surge_mult": 1.5,    # 量能倍數門檻
    "vol_confirm_n":  5,      # 訊號後幾個交易日內出現大量
}


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _macd(close: pd.Series, fast: int, slow: int, sig: int):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=sig, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def add_bbreak_signals(df: pd.DataFrame, cfg: dict = None) -> pd.DataFrame:
    """
    計算布林通道破底翻訊號，回傳加上訊號欄位的新 df。
    cfg 可傳入部分參數覆蓋 CFG 預設值。
    """
    c = {**CFG, **(cfg or {})}
    df = df.copy()
    n = len(df)

    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    open_  = df["open"]

    # ── 必要條件 1：跌破布林下軌 ──────────────────────────────────────────
    bb_mid   = close.rolling(c["bb_period"]).mean()
    bb_std   = close.rolling(c["bb_period"]).std(ddof=1)
    bb_lower = bb_mid - c["bb_std"] * bb_std
    df["bb_lower"] = bb_lower
    df["bb_break"]  = low < bb_lower                          # 最低價跌破下軌

    # ── 必要條件 2：長下影線 ──────────────────────────────────────────────
    body_top    = pd.concat([open_, close], axis=1).max(axis=1)   # min(O,C) 的對立
    body_bottom = pd.concat([open_, close], axis=1).min(axis=1)
    shadow_len  = body_bottom - low                               # 下影線長度
    full_range  = high - low                                      # 全天區間
    # 全天區間為 0（十字線）時跳過，避免除以零
    df["shadow_ratio"] = shadow_len / full_range.replace(0, np.nan)
    df["long_shadow"]  = df["shadow_ratio"] >= c["shadow_ratio"]

    # ── 首次跌破：前一天未破、今天才破（排除持續在下軌以下的連續日） ──
    df["first_bb_break"] = df["bb_break"] & (~df["bb_break"].shift(1, fill_value=False))

    # ── 主訊號：必要條件 1 & 2 同時成立（用首次跌破，不算連續破底） ───
    df["signal"] = df["first_bb_break"] & df["long_shadow"]

    # ── 輔助條件 3：RSI 超賣 ─────────────────────────────────────────────
    if c["use_rsi"]:
        rsi = _rsi(close, c["rsi_period"])
        df["aux_rsi"] = rsi < c["rsi_thresh"]
    else:
        df["aux_rsi"] = False

    # ── 輔助條件 4：MACD 背離 ─────────────────────────────────────────────
    if c["use_macd_div"]:
        _, _, hist = _macd(close, c["macd_fast"], c["macd_slow"], c["macd_signal"])
        lookback = c["div_lookback"]
        div_flags = [False] * n
        for i in range(lookback, n):
            window_close = close.iloc[i - lookback: i + 1]
            window_hist  = hist.iloc[i - lookback: i + 1]
            cur_close = close.iloc[i]
            cur_hist  = hist.iloc[i]
            # 收盤創近期新低
            if cur_close == window_close.min():
                # 找上一次新低（排除當天）
                prev_min_idx = window_close.iloc[:-1].idxmin()
                prev_hist_at_min = hist.loc[prev_min_idx] if prev_min_idx in hist.index else np.nan
                # MACD 柱體高於上次新低時 → 正背離
                if pd.notna(prev_hist_at_min) and cur_hist > prev_hist_at_min:
                    div_flags[i] = True
        df["aux_macd_div"] = div_flags
    else:
        df["aux_macd_div"] = False

    # ── 輔助條件 5：訊號後 N 日內量能放大 ────────────────────────────────
    if c["use_vol_surge"] and "volume" in df.columns:
        vol    = df["volume"]
        vol_ma = vol.rolling(c["vol_ma_period"]).mean()
        is_surge = vol > c["vol_surge_mult"] * vol_ma    # 當天是否放量
        confirm_n = c["vol_confirm_n"]
        surge_flags = [False] * n
        signal_arr  = df["signal"].tolist()
        surge_arr   = is_surge.tolist()
        for i in range(n):
            if signal_arr[i]:
                # 訊號當天 +1 ~ +N 日內有放量
                for k in range(i + 1, min(i + confirm_n + 1, n)):
                    if surge_arr[k]:
                        surge_flags[i] = True
                        break
        df["aux_vol_surge"] = surge_flags
    else:
        df["aux_vol_surge"] = False

    return df


def bbreak_to_chart_markers(df: pd.DataFrame, times: list) -> list:
    """
    把 df 的布林通道破底翻訊號轉成 lightweight-charts markers 格式。
    times：與 df 等長的 time 字串列表（與 main.py 現有 times 對齊）。
    回傳 list of marker dict，直接 extend 進現有 signals 即可。
    """
    markers = []
    for i, (_, row) in enumerate(df.iterrows()):
        if not row.get("signal", False):
            continue
        # 組合文字標籤
        extras = []
        if row.get("aux_rsi", False):
            extras.append("RSI")
        if row.get("aux_macd_div", False):
            extras.append("背離")
        if row.get("aux_vol_surge", False):
            extras.append("放量")
        label = "BB破底翻" + ("+" + "+".join(extras) if extras else "")
        markers.append({
            "time":     times[i],
            "position": "belowBar",
            "shape":    "arrowUp",
            "color":    "#ff6d00",
            "text":     label,
        })
    return markers
