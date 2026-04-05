"""
台股 AI 戰情室 v3.0 集中設定檔 (§11) — 優化版
整合分析建議：ATR停損、Sharpe動能、時間停損、滑價修正
"""

# ── 市場判斷閾值 ──────────────────────────────────────────────
MARKET_SCORE_BULL    = 3     # 總分 >= 3 判定為多頭
MARKET_SCORE_NEUTRAL = 2     # 總分 == 2 判定為中性

# ── 均線參數 ──────────────────────────────────────────────────
MA_SHORT  = 20
MA_MID    = 60
MA_LONG   = 120
MA_ANNUAL = 240   # 年線

# ── 風控參數（優化版）────────────────────────────────────────
MAX_POSITION_PER_STOCK  = 0.10   # 單股最大持倉比重 10%
MAX_PORTFOLIO_DRAWDOWN  = 0.15   # 最大回撤 15%，超過暫停交易
STOP_LOSS_PCT           = 0.08   # 固定停損 -8%（ATR模式下為備援）
TRAILING_STOP_PCT       = 0.07   # 移動停利回撤 7%
MIN_CASH_RATIO          = 0.10   # 現金部位下限 10%
MAX_POSITIONS           = 10     # 最大持股檔數

# ── ATR 動態停損參數（§優化1）────────────────────────────────
ATR_PERIOD     = 14      # ATR 計算週期（天）
ATR_MULTIPLIER = 1.5     # 停損距離 = Entry - (N × ATR14)，N=1.5~2.0

# ── 時間停損參數（§優化5：防止資金被套）────────────────────
TIME_STOP_DAYS      = 15    # 買進後超過 15 天
TIME_STOP_MIN_GAIN  = 0.02  # 若報酬未達 +2% → 強制換股

# ── 多因子評分權重（優化版：加入基本面 15%）────────────────
# 原：趨勢30 / 動能25 / 籌碼20 / 量價15 / 風險10
# 新：趨勢25 / 動能20 / 籌碼20 / 量價15 / 風險10 / 基本面10
WEIGHT_TREND      = 0.25   # 趨勢面（下調 5%）
WEIGHT_MOMENTUM   = 0.20   # 動能面：改用 Sharpe-like（下調 5%）
WEIGHT_CHIP       = 0.20   # 籌碼面
WEIGHT_VOLUME     = 0.15   # 量價面
WEIGHT_RISK       = 0.10   # 風險面
WEIGHT_FUNDAMENTAL= 0.10   # 基本面（月營收YoY + 毛利率）新增

# ── 動態因子權重表（依市場狀態自動切換）────────────────────
# bull：趨勢/動能加重，進攻型；bear：風險/基本面加重，防禦型
WEIGHT_TABLES = {
    'bull': {
        'trend': 0.30, 'momentum': 0.25, 'chip': 0.20,
        'volume': 0.15, 'risk': 0.05, 'fundamental': 0.05,
    },
    'neutral': {
        'trend': 0.25, 'momentum': 0.20, 'chip': 0.20,
        'volume': 0.15, 'risk': 0.10, 'fundamental': 0.10,
    },
    'bear': {
        'trend': 0.15, 'momentum': 0.10, 'chip': 0.15,
        'volume': 0.15, 'risk': 0.25, 'fundamental': 0.20,
    },
}

# ── 選股篩選條件 ──────────────────────────────────────────────
TOP_N_STOCKS    = 10
RSI_OVERBOUGHT  = 70
RSI_OVERSOLD    = 30
MIN_LIQUIDITY   = 500

# ── 回測參數（優化版：滑價提高至 0.003）─────────────────────
BACKTEST_INIT_CASH    = 1_000_000
BACKTEST_COMMISSION   = 0.001425    # 台股手續費 0.1425%
BACKTEST_SLIPPAGE     = 0.003       # 滑價：提高至 0.3%（更貼近實戰）
WFT_TRAIN_YEARS       = 3
WFT_TEST_MONTHS       = 12

# ── 市場曝險比例（依 market_regime）────────────────────────
EXPOSURE_BULL    = 0.80   # 多頭：80% 持股
EXPOSURE_NEUTRAL = 0.50   # 中性：50% 持股
EXPOSURE_BEAR    = 0.20   # 空頭：20% 持股

# ── 韭菜指數警戒門檻 ─────────────────────────────────────────
LEEK_HIGH_THRESHOLD  = 35.0   # 超過此值 = 散戶過熱，警戒
LEEK_LOW_THRESHOLD   = 10.0   # 低於此值 = 散戶淨空，潛在機會

# ── 瘋牛濾網（量能過濾韭菜指數）────────────────────────────
BULLRUN_VOL_THRESHOLD = 1.3   # 大盤成交量 > 月均量 x 1.3 = 資金派對模式

