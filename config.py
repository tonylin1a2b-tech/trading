# config.py — 全域常數：顏色、TTL、Headers

# ── 台股慣例色（紅漲綠跌）──────────────────────────────
COLOR_UP      = "#c0392b"   # 漲
COLOR_DOWN    = "#27ae60"   # 跌
COLOR_NEUTRAL = "#888"

# ── K線圖蠟燭顏色（Plotly / LightweightCharts）──────────
CANDLE_UP   = "#ef5350"
CANDLE_DOWN = "#26a69a"

# ── 快取 TTL（秒）────────────────────────────────────────
TTL_REALTIME    = 300       # 5 分鐘：即時報價
TTL_INTRADAY    = 1_800     # 30 分鐘：盤中指標
TTL_DAILY       = 14_400    # 4 小時：日線/籌碼
TTL_CALENDAR    = 21_600    # 6 小時：總經行事曆
TTL_KLINE       = 900       # 15 分鐘：K線資料
TTL_FUNDAMENTAL = 86_400    # 1 天：財報/月營收

# ── HTTP Headers（TAIFEX / TWSE 需要）────────────────────
MARKET_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/x-www-form-urlencoded",
}
