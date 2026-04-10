"""
股票多因子評分引擎 v3.0 (§5.2-5.4)
評分維度：趨勢 / 動能 / 籌碼 / 量價 / 風險
加權公式：0.30 / 0.25 / 0.20 / 0.15 / 0.10
"""

try:
    from config import (WEIGHT_TREND, WEIGHT_MOMENTUM, WEIGHT_CHIP,
                        WEIGHT_VOLUME, WEIGHT_RISK,
                        RSI_OVERBOUGHT, RSI_OVERSOLD, WEIGHT_TABLES)
except ImportError:
    WEIGHT_TREND=0.30; WEIGHT_MOMENTUM=0.25; WEIGHT_CHIP=0.20
    WEIGHT_VOLUME=0.15; WEIGHT_RISK=0.10
    RSI_OVERBOUGHT=70; RSI_OVERSOLD=30
    WEIGHT_TABLES = {
        'bull':    {'trend':0.30,'momentum':0.25,'chip':0.20,'volume':0.15,'risk':0.05,'fundamental':0.05},
        'neutral': {'trend':0.25,'momentum':0.20,'chip':0.20,'volume':0.15,'risk':0.10,'fundamental':0.10},
        'bear':    {'trend':0.15,'momentum':0.10,'chip':0.15,'volume':0.15,'risk':0.25,'fundamental':0.20},
    }


# ── 1. 趨勢分數 ───────────────────────────────────────────────
def calc_trend_score(df) -> float:
    """
    趨勢分數（0-100）
    修正：
    1. 資料不足 → 0分（不得中性假分）
    2. 預設值改為 0，避免「無MA=不站上」被誤判為站上
    3. 加入 MA 斜率加分（短均 > 長均 且向上彎折）
    """
    if df is None or df.empty or 'close' not in df.columns:
        return 0.0   # 無資料 → 0分，不混入推薦名單
    if len(df) < 60:
        return 0.0   # 資料不足 → 0分
    close = df['close']
    score = 0; total = 5
    for period in [5, 20, 60, 120]:
        col = f'MA{period}'
        if col not in df.columns:
            df[col] = close.rolling(period).mean()
    latest  = df.iloc[-1]
    prev    = df.iloc[-2] if len(df) >= 2 else latest
    c = float(latest['close'])

    # 條件1: 價格站上各均線（預設值0，避免無MA被算成站上）
    ma5  = latest.get('MA5',  0) or 0
    ma20 = latest.get('MA20', 0) or 0
    ma60 = latest.get('MA60', 0) or 0
    ma120= latest.get('MA120',0) or 0

    if ma5  > 0 and c > ma5:   score += 1   # 價站MA5（短線）
    if ma20 > 0 and c > ma20:  score += 1   # 價站MA20（中線）
    if ma60 > 0 and c > ma60:  score += 1   # 價站MA60（中長線）

    # 條件2: 均線多頭排列（MA20>MA60>MA120）
    if ma20 > 0 and ma60 > 0 and ma20 > ma60:   score += 1  # MA20>MA60
    if ma60 > 0 and ma120 > 0 and ma60 > ma120: score += 1  # MA60>MA120

    return round(score / total * 100, 1)


# ── 2. 動能分數 (§5.3 優化版：Sharpe-like 波動調整後報酬) ────
def calc_momentum_score(df) -> float:
    """
    動能分數（0-100）— 升級版：解決共線性問題
    核心邏輯：波動調整後報酬 = Return20 / Sigma20（類 Sharpe）
    「緩步穩健上漲」優先於「暴漲但震盪極大」
    """
    if df is None or len(df) < 20:
        return 0.0   # 資料不足→0分，不得假中性分
    close = df['close']

    # ① RSI 區間評分
    if 'RSI' not in df.columns:
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        df['RSI'] = 100 - 100 / (1 + gain / (loss + 1e-10))
    rsi = df['RSI'].iloc[-1]
    rsi_score = 2 if RSI_OVERSOLD < rsi < RSI_OVERBOUGHT else (1 if rsi <= RSI_OVERSOLD else 0)

    # ② Sharpe-like 動能（20日）
    # Return20 / Sigma20：緩步上漲 > 暴漲暴跌
    ret20  = (close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0
    sigma20 = close.pct_change().rolling(20).std().iloc[-1] if len(close) >= 20 else 0.01
    sharpe_20 = ret20 / (sigma20 * (20 ** 0.5) + 1e-10)  # 年化 Sharpe 代理
    sharpe_score = 2 if sharpe_20 > 0.5 else (1 if sharpe_20 > 0 else 0)

    # ③ ATR 動態停損空間（股票波動度 vs 風險）
    if len(df) >= 14:
        _hi = df['high'] if 'high' in df.columns else close
        _lo = df['low']  if 'low'  in df.columns else close
        _tr = (_hi - _lo).rolling(14).mean().iloc[-1]
        _atr_pct = _tr / close.iloc[-1] if close.iloc[-1] > 0 else 0.02
        # ATR% < 3% = 低波動性質，穩健；ATR% > 5% = 高波動，酌扣
        atr_score = 2 if _atr_pct < 0.03 else (1 if _atr_pct < 0.05 else 0)
    else:
        atr_score = 1

    total_raw = rsi_score + sharpe_score + atr_score  # 最高 6 分
    return round(min(total_raw / 6 * 100, 100), 1)


def momentum_signal(df) -> bool:
    """
    主力動能篩選訊號（§5.3）
    條件：收盤 > MA20、MA20 > MA60、成交量 > 20日均量
    """
    if df is None or df.empty:
        return False
    for p in [20, 60]:
        if f'MA{p}' not in df.columns:
            df[f'MA{p}'] = df['close'].rolling(p).mean()
    if 'VOL20' not in df.columns:
        df['VOL20'] = df['volume'].rolling(20).mean()
    latest = df.iloc[-1]
    return (
        latest['close'] > latest.get('MA20', latest['close'])
        and latest.get('MA20', 0) > latest.get('MA60', 0)
        and latest['volume'] > latest.get('VOL20', 0)
    )


# ── 3. 籌碼分數 (§5.4) ────────────────────────────────────────
def chip_score(foreign_buy, trust_buy=0, dealer_buy=0) -> int:
    """
    法人籌碼評分（§5.4）
    外資買超 +2、投信買超 +2、自營商買超 +1
    最高 5 分
    """
    score = 0
    if foreign_buy > 0: score += 2
    if trust_buy   > 0: score += 2
    if dealer_buy  > 0: score += 1
    return score


def calc_chip_score(df, foreign_buy=None, trust_buy=None, dealer_buy=None) -> float:
    """
    籌碼分數（0-100）
    修正：股價 DataFrame 不含籌碼欄位，必須額外傳入法人數據
    若無法人數據，回傳 50（中性），並在 score_single_stock 中明確標記
    """
    if foreign_buy is not None:
        raw = chip_score(foreign_buy or 0, trust_buy or 0, dealer_buy or 0)
        return round(raw / 5 * 100, 1)
    # 嘗試從 df 讀取（若有整合籌碼欄位）
    if df is not None and not df.empty:
        latest = df.iloc[-1]
        fb = latest.get('外資買超', latest.get('外資', None))
        tb = latest.get('投信買超', latest.get('投信', None))
        db = latest.get('自營買超', latest.get('自營商', None))
        if fb is not None:
            raw = chip_score(float(fb or 0), float(tb or 0), float(db or 0))
            return round(raw / 5 * 100, 1)
    return 50.0  # 無籌碼資料 → 中性（不加分不扣分）


# ── 4. 量價分數 ───────────────────────────────────────────────
def calc_volume_score(df) -> float:
    """
    量價分數（0-100）
    條件：量增價漲、成交量高於均量、價格不縮量破線
    """
    if df is None or len(df) < 20:
        return 50.0
    score = 0; total = 3
    close  = df['close']
    volume = df['volume']
    vol20  = volume.rolling(20).mean()

    # 量能放大
    if volume.iloc[-1] > vol20.iloc[-1]:
        score += 1
    # 量增價漲（近3日）
    if len(df) >= 3:
        price_up  = close.iloc[-1] > close.iloc[-3]
        vol_up    = volume.iloc[-1] > volume.iloc[-3]
        if price_up and vol_up:
            score += 1
    # 最近5日成交量均值 > 20日均量（持續活躍）
    if volume.tail(5).mean() > vol20.iloc[-1]:
        score += 1

    return round(score / total * 100, 1)


# ── 5. 風險分數 ───────────────────────────────────────────────
def calc_risk_score(df) -> float:
    """
    風險分數（0-100，越高越低風險）
    修正：
    P2: 波動率門檻由固定3%改為相對分級（台股中型股平均3-5%）
    P3: MA60 NaN 保護（資料不足60天時不計此條）
    """
    if df is None or len(df) < 20:
        return 0.0   # 資料不足→0分
    close = df['close']
    score = 0; total = 3

    # 波動率分級（修正：台股日波動率通常1.5%-6%）
    vol_pct = close.pct_change().rolling(20).std().iloc[-1]
    if   vol_pct < 0.02:  score += 1   # 極低波動（ETF/權值股）
    elif vol_pct < 0.035: score += 1   # 正常低波動（原門檻3%已鬆寬）
    # 3.5%~5% → 0分，>5% → 0分（高波動高風險）

    # RSI 不超買
    if 'RSI' not in df.columns:
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        df['RSI'] = 100 - 100 / (1 + gain / (loss + 1e-10))
    rsi_val = df['RSI'].iloc[-1]
    if not (rsi_val != rsi_val):   # NaN check
        if rsi_val < RSI_OVERBOUGHT:
            score += 1

    # 站上 MA60（NaN 保護：資料不足60天時不計，給中立0.5分）
    if 'MA60' not in df.columns:
        df['MA60'] = close.rolling(60).mean()
    ma60_val = df['MA60'].iloc[-1]
    if ma60_val != ma60_val:   # NaN（資料不足60天）
        score += 0.5           # 中立，不加不扣
    elif close.iloc[-1] >= ma60_val:
        score += 1

    return round(min(score / total * 100, 100), 1)


# ── 核心：多因子加權評分 (§5.2) ───────────────────────────────
def stock_score(trend, momentum, chip, volume_score, risk_score,
               fundamental_score=50.0, regime: str = 'neutral') -> float:
    """
    多因子加權總分（v3.2 動態權重版）
    regime='bull'|'neutral'|'bear' 自動切換因子權重表
    """
    try:
        from config import WEIGHT_TABLES, WEIGHT_FUNDAMENTAL
    except ImportError:
        WEIGHT_TABLES = {
            'bull':    {'trend':0.30,'momentum':0.25,'chip':0.20,'volume':0.15,'risk':0.05,'fundamental':0.05},
            'neutral': {'trend':0.25,'momentum':0.20,'chip':0.20,'volume':0.15,'risk':0.10,'fundamental':0.10},
            'bear':    {'trend':0.15,'momentum':0.10,'chip':0.15,'volume':0.15,'risk':0.25,'fundamental':0.20},
        }
        WEIGHT_FUNDAMENTAL = 0.10
    w = WEIGHT_TABLES.get(regime, WEIGHT_TABLES['neutral'])
    return round(
        trend             * w['trend']       +
        momentum          * w['momentum']    +
        chip              * w['chip']        +
        volume_score      * w['volume']      +
        risk_score        * w['risk']        +
        fundamental_score * w['fundamental'],
        1)



# ── RS 相對強度（Relative Strength）─────────────────────────
def calc_rs_score(df, df_index=None, period=250):
    """
    RS = 個股 N日漲幅 / 大盤 N日漲幅
    RS > 1.5  → 強勢，RS_score = 高分
    RS < 0.5  → 弱勢，RS_score = 低分
    """
    try:
        if df is None or len(df) < 20: return 50
        close = df['close'].dropna()
        n = min(period, len(close)-1)
        if n < 5: return 50
        stock_chg = (close.iloc[-1] / close.iloc[-n] - 1) * 100

        # 大盤基準：若有傳入則用，否則用固定基準
        if df_index is not None and len(df_index) >= n:
            cc = 'Close' if 'Close' in df_index.columns else 'close'
            idx_chg = (df_index[cc].iloc[-1] / df_index[cc].iloc[-n] - 1) * 100
        else:
            # 無大盤資料時用 0 為基準（只看絕對漲幅）
            idx_chg = 0

        if idx_chg == 0:
            # 無大盤基準：直接用絕對漲幅映射，不套入相對公式
            # 避免與有基準時的 rs 數值系統不同造成混淆
            if stock_chg >= 50:   return 100
            elif stock_chg >= 30: return 90
            elif stock_chg >= 15: return 75
            elif stock_chg >= 5:  return 60
            elif stock_chg >= 0:  return 50
            else:                 return max(20, 50 + stock_chg)
        else:
            rs = stock_chg / abs(idx_chg)

        # 映射到 0-100 分
        if rs >= 2.0:   return 100
        elif rs >= 1.5: return 90
        elif rs >= 1.0: return 75
        elif rs >= 0.5: return 55
        elif rs >= 0.0: return 40
        else:           return 20
    except: return 50

def rs_slope(df, df_index=None, window=20):
    """RS 曲線斜率：最近20日 RS 趨勢向上=True"""
    try:
        if df is None or len(df) < window + 10: return None
        close = df['close'].dropna()
        rs_series = []
        for i in range(window):
            n = len(close) - window + i
            if n < 5: continue
            chg = (close.iloc[n] / close.iloc[max(0,n-20)] - 1) * 100
            rs_series.append(chg)
        if len(rs_series) < 5: return None
        # 線性迴歸斜率
        import numpy as np
        x = list(range(len(rs_series)))
        slope = np.polyfit(x, rs_series, 1)[0]
        return slope > 0
    except: return None

def score_single_stock(df, stock_id='', stock_name='', **kwargs) -> dict:
    """
    對單一股票進行完整多因子評分

    Args:
        df: StockDataLoader 提供的 OHLCV DataFrame
        kwargs: foreign_buy, trust_buy, dealer_buy, revenue_df,
                regime ('bull'|'neutral'|'bear'),
                short_ratio (float, 券資比 0~1),
                inst_consec_buy (int, 法人連買天數)
    Returns:
        dict: 各維度分數 + 總分 + 動能訊號 + 評級
    """
    if df is None or df.empty:
        return {'stock_id': stock_id, 'total': 0, 'error': '無資料'}

    t_score = calc_trend_score(df)
    m_score = calc_momentum_score(df)
    # 籌碼分數：優先用外部傳入的法人數據
    c_score = calc_chip_score(df,
                               foreign_buy=kwargs.get('foreign_buy'),
                               trust_buy=kwargs.get('trust_buy'),
                               dealer_buy=kwargs.get('dealer_buy'))
    v_score = calc_volume_score(df)
    r_score = calc_risk_score(df)
    # 基本面分數（月營收YoY動能）
    f_score = calc_fundamental_score(kwargs.get('revenue_df'))

    regime = kwargs.get('regime', 'neutral')
    total = stock_score(t_score, m_score, c_score, v_score, r_score, f_score, regime=regime)

    # 軋空加分：券資比 > 30% 且 法人連買 ≥ 3 天 → +5 分
    squeeze_bonus = calc_short_squeeze_bonus(
        short_ratio=kwargs.get('short_ratio', 0.0),
        inst_consecutive_buy=kwargs.get('inst_consec_buy', 0),
    )
    total = round(min(100.0, total + squeeze_bonus['bonus']), 1)

    mom_sig = momentum_signal(df)

    if total >= 75:
        grade = 'A'
    elif total >= 55:
        grade = 'B'
    else:
        grade = 'C'

    vcp_atr = check_vcp_atr_filter(df)

    return {
        'stock_id':    stock_id,
        'stock_name':  stock_name,
        'trend':       t_score,
        'momentum':    m_score,
        'chip':        c_score,
        'volume':      v_score,
        'risk':        r_score,
        'total':       total,
        'grade':       grade,
        'momentum_signal': mom_sig,
        'regime':      regime,
        'squeeze_bonus': squeeze_bonus['bonus'],
        'squeeze_label': squeeze_bonus['label'],
        'vcp_atr_pass':  vcp_atr['pass'],
        'vcp_atr_label': vcp_atr['label'],
    }


def rank_stocks(results: list) -> list:
    """
    對多檔股票評分結果排序（高分在前）
    Args:
        results: list of score_single_stock() 結果
    Returns:
        排序後的 list
    """
    valid = [r for r in results if 'error' not in r]
    return sorted(valid, key=lambda x: x['total'], reverse=True)

# ════════════════════════════════════════════════════════════
# 優化新增函式（v3.1）
# ════════════════════════════════════════════════════════════

# ── 基本面分數（月營收YoY動能）──────────────────────────────
def calc_fundamental_score(revenue_df=None, yoy_months: int = 3) -> float:
    """
    基本面動能分數（0-100）
    月營收 YoY 連續成長 + 加速度判斷
    無財報數據時回傳中性值 50
    """
    if revenue_df is None or isinstance(revenue_df, list) or not hasattr(revenue_df, 'empty') or revenue_df.empty:
        return 50.0
    try:
        if 'yoy' not in revenue_df.columns and 'revenue' in revenue_df.columns:
            revenue_df = revenue_df.copy()
            revenue_df['yoy'] = revenue_df['revenue'].pct_change(12) * 100
        recent = revenue_df.dropna(subset=['yoy']).tail(yoy_months)
        if len(recent) < 1:
            return 50.0
        score = 0; total = 4
        # ① 連續 N 個月 YoY > 0
        if len(recent) >= yoy_months and (recent['yoy'] > 0).all():
            score += 2
        elif (recent['yoy'] > 0).sum() >= max(1, yoy_months - 1):
            score += 1
        # ② YoY 加速（最新月 > 前月）
        if len(recent) >= 2 and recent['yoy'].iloc[-1] > recent['yoy'].iloc[-2]:
            score += 1
        # ③ YoY > 15%（強勁成長）
        if recent['yoy'].iloc[-1] > 15:
            score += 1
        return round(min(score / total * 100, 100), 1)
    except:
        return 50.0


# ── 獲利品質得分 (SQ) ────────────────────────────────────────
def calc_quality_score(quarterly_df=None) -> dict:
    """
    獲利品質得分 (SQ) = 毛利趨勢 × 營收趨勢的交叉評分（0~100）
    SQ = WGM(40%) × SGM_Level + WTrend(60%) × Sraw_norm

    Sraw 交叉分表：
      ↑GM + ↑Rev = +2.0（最佳：毛利擴張同時營收成長）
      →GM + ↑Rev = +1.5（穩健：毛利持穩但營收成長）
      ↓GM + ↑Rev =  0.0（警示：毛利縮水但量能支撐）
      ↑GM + ↓Rev = +0.5（謹慎：毛利改善但量能萎縮）
      ↓GM + ↓Rev = -2.0（最差：量利雙降）

    SGM_Level（毛利率絕對值評分）：>50% → 100，<10% → 40，線性內插。

    回傳 dict: sq(0-100 or None), sq_label, gm_trend(↑/↓/→), rev_trend(↑/↓), gm_level(%)
    """
    _empty = {'sq': None, 'sq_label': '-', 'gm_trend': '-', 'rev_trend': '-', 'gm_level': None}
    if quarterly_df is None or not hasattr(quarterly_df, 'empty') or quarterly_df.empty:
        return _empty
    try:
        import pandas as _pd_sq
        if '毛利率' not in quarterly_df.columns or '營收' not in quarterly_df.columns:
            return _empty

        gm_vals  = _pd_sq.to_numeric(quarterly_df['毛利率'], errors='coerce').dropna()
        rev_vals = _pd_sq.to_numeric(quarterly_df['營收'],   errors='coerce').dropna()

        if len(gm_vals) < 2 or len(rev_vals) < 2:
            return _empty

        # 毛利率趨勢：近2季平均 vs 前2季平均（差距>1個百分點才算顯著）
        gm_recent = gm_vals.iloc[-2:].mean()
        gm_prev   = gm_vals.iloc[-4:-2].mean() if len(gm_vals) >= 4 else gm_vals.iloc[:-2].mean()
        gm_diff   = gm_recent - gm_prev
        if   gm_diff >  1.0: gm_trend = '↑'
        elif gm_diff < -1.0: gm_trend = '↓'
        else:                gm_trend = '→'   # 持穩

        # 營收趨勢：近2季平均 vs 前2季平均（需成長>2%才算↑）
        rev_recent = rev_vals.iloc[-2:].mean()
        rev_prev   = rev_vals.iloc[-4:-2].mean() if len(rev_vals) >= 4 else rev_vals.iloc[:-2].mean()
        rev_trend  = '↑' if rev_prev > 0 and rev_recent > rev_prev * 1.02 else '↓'

        # 交叉評分 Sraw
        if   gm_trend == '↑' and rev_trend == '↑': sraw = 2.0
        elif gm_trend == '→' and rev_trend == '↑': sraw = 1.5
        elif gm_trend == '↓' and rev_trend == '↑': sraw = 0.0
        elif gm_trend == '↑' and rev_trend == '↓': sraw = 0.5
        else:                                       sraw = -2.0   # ↓GM + ↓Rev

        # SGM_Level：毛利率絕對值評分（40~100）
        gm_level = float(gm_vals.iloc[-1])
        if   gm_level >= 50: sgm = 100.0
        elif gm_level <= 10: sgm = 40.0
        else:                sgm = 40.0 + (gm_level - 10) / 40.0 * 60.0

        # SQ 合成：Sraw 正規化至 0~100
        sraw_norm = (sraw + 2.0) / 4.0 * 100.0
        sq = round(0.4 * sgm + 0.6 * sraw_norm, 1)

        if   sq >= 75: sq_label = '優質'
        elif sq >= 55: sq_label = '穩健'
        elif sq >= 40: sq_label = '普通'
        else:          sq_label = '弱'

        return {'sq': sq, 'sq_label': sq_label,
                'gm_trend': gm_trend, 'rev_trend': rev_trend,
                'gm_level': round(gm_level, 1)}
    except Exception:
        return _empty


# ── 前瞻成長動能分數 (FGMS) ────────────────────────────────
def calc_forward_momentum_score(quarterly_df=None, bs_cf_df=None,
                                 is_finance: bool = False) -> dict:
    """
    前瞻成長動能分數 (Forward Growth Momentum Score, FGMS) = 0~100

    公式與權重：
      合約負債動能    40%  — CL Ratio QoQ 成長速度
      存貨營收背離率  30%  — Revenue YoY% - Inventory Days YoY%（服務業/無存貨跳過）
      三率趨勢        20%  — 毛利率+營業利益率+淨利率同步方向
      資本支出強度    10%  — CapEx YoY 成長（對未來產能的信心）

    邊界處理：
      - CL Ratio 爆炸值：clip至 [0, 5]
      - 服務業/無存貨：inventory 維度跳過，權重移至三率
      - 合約負債全空：權重移至三率+資本支出
      - 去年同期負數的 YoY：clip至 [-200%, +300%]
      - 資本支出 YoY 暴增（一次性購地）：cap at +100%

    回傳 dict: fgms(0-100 or None), fgms_label, 分項 dict
    """
    import numpy as np
    _empty = {'fgms': None, 'fgms_label': '-',
              'cl_momentum': None, 'inv_divergence': None,
              'three_rate': None, 'capex_intensity': None}

    try:
        # ── 共用函數 ────────────────────────────────────────
        def _safe_yoy(series, periods=4):
            """YoY% = (now - prev_year) / |prev_year| × 100, 處理負基期 & NaN"""
            if len(series) <= periods: return float('nan')
            now  = series.iloc[-1]
            prev = series.iloc[-1 - periods]
            if pd.isna(now) or pd.isna(prev) or prev == 0: return float('nan')
            raw = (now - prev) / abs(prev) * 100
            return float(np.clip(raw, -200, 300))

        def _qoq_pct(series):
            """QoQ% 最近一季 vs 前一季"""
            clean = pd.to_numeric(series, errors='coerce').dropna()
            if len(clean) < 2: return float('nan')
            prev = clean.iloc[-2]; now = clean.iloc[-1]
            if prev == 0: return float('nan')
            raw = (now - prev) / abs(prev) * 100
            return float(np.clip(raw, -200, 300))

        # ══════════════════════════════════════════════════════
        # 維度 1 — 合約負債動能（40%）
        # ══════════════════════════════════════════════════════
        cl_score = None
        if bs_cf_df is not None and not bs_cf_df.empty and '合約負債' in bs_cf_df.columns:
            cl_series = pd.to_numeric(bs_cf_df['合約負債'], errors='coerce').dropna()
            if len(cl_series) >= 4 and quarterly_df is not None:
                rev_series = pd.to_numeric(quarterly_df['營收'], errors='coerce').dropna().tail(4)
                rev_avg = rev_series.mean() if len(rev_series) >= 2 else float('nan')
                if rev_avg > 0:
                    # CL Ratio = 最新合約負債 / 近4季平均營收
                    cl_latest = cl_series.iloc[-1]
                    cl_ratio  = float(np.clip(cl_latest / rev_avg, 0, 5))
                    cl_qoq    = _qoq_pct(cl_series)   # QoQ 加速？
                    # 評分：CL Ratio 深度 + QoQ 動能雙軌
                    if   cl_ratio > 0.5 and not pd.isna(cl_qoq) and cl_qoq > 10: cl_score = 100
                    elif cl_ratio > 0.5 or (not pd.isna(cl_qoq) and cl_qoq > 10): cl_score = 75
                    elif cl_ratio > 0.2:  cl_score = 55
                    elif cl_ratio > 0.05: cl_score = 40
                    elif not pd.isna(cl_qoq) and cl_qoq < -10: cl_score = 20
                    else:                 cl_score = 35
                else:
                    cl_score = None  # rev_avg 無效

        # ══════════════════════════════════════════════════════
        # 維度 2 — 存貨營收背離率（30%）
        # ══════════════════════════════════════════════════════
        inv_score = None
        has_inventory = False
        if bs_cf_df is not None and not bs_cf_df.empty and '存貨' in bs_cf_df.columns:
            inv_series = pd.to_numeric(bs_cf_df['存貨'], errors='coerce').dropna()
            has_inventory = len(inv_series) >= 2 and inv_series.iloc[-1] > 0
        if has_inventory and quarterly_df is not None and '營收' in quarterly_df.columns:
            rev_qs = pd.to_numeric(quarterly_df['營收'], errors='coerce').dropna()
            rev_yoy = _safe_yoy(rev_qs, periods=4)
            # 存貨天數 YoY = (inv_days_now - inv_days_prev) / |inv_days_prev| × 100
            # inv_days = 存貨 / (近4季總營收 / 365)
            def _inv_days(df_q, df_extra):
                if len(inv_series) < 2: return float('nan')
                _rev_ttm = pd.to_numeric(df_q['營收'], errors='coerce').dropna().tail(4).sum()
                _inv = pd.to_numeric(df_extra['存貨'], errors='coerce').dropna().iloc[-1]
                if _rev_ttm <= 0: return float('nan')
                return _inv / (_rev_ttm / 365)
            inv_days_now  = _inv_days(quarterly_df, bs_cf_df)
            # 一年前版本（bs_cf_df 最前4筆 vs 最後4筆）
            _bs_prev = bs_cf_df.iloc[:-4] if len(bs_cf_df) > 4 else bs_cf_df.head(1)
            _qtr_prev = quarterly_df.iloc[:-4] if len(quarterly_df) > 4 else quarterly_df.head(2)
            inv_days_prev = _inv_days(_qtr_prev, _bs_prev) if not _qtr_prev.empty else float('nan')
            if not pd.isna(inv_days_prev) and inv_days_prev != 0:
                inv_days_yoy = float(np.clip((inv_days_now - inv_days_prev) / abs(inv_days_prev) * 100, -200, 300))
            else:
                inv_days_yoy = float('nan')
            if not pd.isna(rev_yoy) and not pd.isna(inv_days_yoy):
                divergence = rev_yoy - inv_days_yoy   # 正值 = 好（賣得快）
                if   divergence > 15:  inv_score = 100
                elif divergence > 5:   inv_score = 75
                elif divergence >= -5: inv_score = 50
                elif divergence >= -15:inv_score = 30
                else:                  inv_score = 10
            elif not pd.isna(rev_yoy):
                inv_score = 65 if rev_yoy > 10 else (50 if rev_yoy > 0 else 30)

        # ══════════════════════════════════════════════════════
        # 維度 3 — 三率趨勢（20%）
        # ══════════════════════════════════════════════════════
        three_rate_score = None
        if quarterly_df is not None and not quarterly_df.empty:
            _rates_up = 0; _rates_total = 0
            for _rcol in ['毛利率', '營業利益率', '淨利率']:
                if _rcol in quarterly_df.columns:
                    _rs = pd.to_numeric(quarterly_df[_rcol], errors='coerce').dropna()
                    if len(_rs) >= 2:
                        _rates_total += 1
                        _recent = _rs.iloc[-2:].mean()
                        _prev   = _rs.iloc[-4:-2].mean() if len(_rs) >= 4 else _rs.iloc[:-2].mean()
                        if _recent > _prev + 0.5: _rates_up += 1
                        elif _recent < _prev - 0.5: _rates_up -= 1  # 惡化
            if _rates_total > 0:
                _ratio = _rates_up / _rates_total   # -1 ~ +1
                three_rate_score = round(50 + _ratio * 50, 1)   # 0 ~ 100

        # ══════════════════════════════════════════════════════
        # 維度 4 — 資本支出強度（10%）
        # ══════════════════════════════════════════════════════
        capex_score = None
        if bs_cf_df is not None and not bs_cf_df.empty and '資本支出' in bs_cf_df.columns:
            cx_series = pd.to_numeric(bs_cf_df['資本支出'], errors='coerce').dropna()
            if len(cx_series) >= 4:
                cx_now   = cx_series.tail(4).sum()
                cx_prev  = cx_series.iloc[-8:-4].sum() if len(cx_series) >= 8 else cx_series.head(4).sum()
                if cx_prev > 0:
                    cx_yoy = float(np.clip((cx_now - cx_prev) / cx_prev * 100, -100, 100))
                    if   cx_yoy > 20:  capex_score = 100
                    elif cx_yoy > 0:   capex_score = 70
                    elif cx_yoy > -20: capex_score = 45
                    else:              capex_score = 20

        # ══════════════════════════════════════════════════════
        # 動態加權（缺少維度時重新分配）
        # ══════════════════════════════════════════════════════
        _w = {'cl': 0.40, 'inv': 0.30, 'three': 0.20, 'capex': 0.10}
        _scores = {'cl': cl_score, 'inv': inv_score, 'three': three_rate_score, 'capex': capex_score}

        # 無合約負債（服務業/金融）→ 把 CL 40% 移到三率
        if _scores['cl'] is None:
            _w['three'] += _w['cl']; _w['cl'] = 0
        # 無存貨（服務業）→ 把 INV 30% 均分給三率+資本支出
        if _scores['inv'] is None or not has_inventory:
            _w['three'] += _w['inv'] * 0.7
            _w['capex'] += _w['inv'] * 0.3
            _w['inv'] = 0
        # 無資本支出 → 移到三率
        if _scores['capex'] is None:
            _w['three'] += _w['capex']; _w['capex'] = 0

        total_w = sum(w for k, w in _w.items() if _scores[k] is not None)
        if total_w <= 0:
            return _empty

        fgms = sum(_w[k] * _scores[k] for k in _w if _scores[k] is not None and _w[k] > 0) / total_w
        fgms = round(fgms, 1)

        if   fgms >= 75: fgms_label = '前景亮麗'
        elif fgms >= 60: fgms_label = '動能向上'
        elif fgms >= 45: fgms_label = '持平觀察'
        elif fgms >= 30: fgms_label = '動能減弱'
        else:            fgms_label = '前景偏弱'

        return {
            'fgms': fgms, 'fgms_label': fgms_label,
            'cl_momentum': round(cl_score, 1) if cl_score is not None else None,
            'inv_divergence': round(inv_score, 1) if inv_score is not None else None,
            'three_rate': round(three_rate_score, 1) if three_rate_score is not None else None,
            'capex_intensity': round(capex_score, 1) if capex_score is not None else None,
        }
    except Exception as _ef:
        print(f'[FGMS] 計算失敗: {_ef}')
        return _empty


# ── ATR 動態停損計算 ────────────────────────────────────────
def calc_atr_stop(df, entry_price: float, multiplier: float = 1.5) -> dict:
    """
    ATR 動態停損點
    Stop_Loss = Entry - (multiplier × ATR14)
    解決固定停損8%過於剛性的問題
    """
    if df is None or len(df) < 14:
        return {'stop_loss': round(entry_price * 0.92, 2),
                'atr': None, 'stop_pct': 8.0, 'method': 'fixed_8pct'}
    try:
        hi = df['high'] if 'high' in df.columns else df['close']
        lo = df['low']  if 'low'  in df.columns else df['close']
        tr = (hi - lo).rolling(14).mean()
        atr = float(tr.iloc[-1])
        stop = entry_price - multiplier * atr
        stop_pct = (entry_price - stop) / entry_price * 100
        return {
            'stop_loss': round(stop, 2),
            'atr': round(atr, 2),
            'stop_pct': round(stop_pct, 1),
            'method': f'ATR14×{multiplier}',
        }
    except:
        return {'stop_loss': round(entry_price * 0.92, 2),
                'atr': None, 'stop_pct': 8.0, 'method': 'fixed_8pct'}


# ── 時間停損判斷 ────────────────────────────────────────────
def check_time_stop(entry_price: float, current_price: float,
                    hold_days: int,
                    min_gain: float = 0.02, max_days: int = 15) -> dict:
    """
    時間停損：防止資金被低效套牢（溫水煮青蛙效應）
    持倉超過 max_days 天但報酬不足 min_gain → 建議換股
    """
    gain = (current_price - entry_price) / entry_price
    triggered = hold_days >= max_days and gain < min_gain
    return {
        'triggered': triggered,
        'hold_days': hold_days,
        'gain_pct': round(gain * 100, 2),
        'message': (f'⏰ 時間停損：持有 {hold_days} 天，報酬僅 {gain*100:.1f}%，建議換股'
                    if triggered else
                    f'持倉 {hold_days} 天，報酬 {gain*100:.1f}%，繼續持有'),
    }

# ── VCP 個股 ATR 濾網 ──────────────────────────────────────
def check_vcp_atr_filter(df) -> dict:
    """
    VCP 波動率收縮確認：ATR5 < ATR20 × 0.8
    短期波動低於中期波動 80% → 收縮確認，VCP 品質良好
    """
    result = {'pass': False, 'atr5': None, 'atr20': None, 'label': ''}
    if df is None or len(df) < 25:
        result['label'] = '資料不足'
        return result
    try:
        hi = df['high'] if 'high' in df.columns else df['close']
        lo = df['low']  if 'low'  in df.columns else df['close']
        tr = (hi - lo)
        atr5  = float(tr.rolling(5).mean().iloc[-1])
        atr20 = float(tr.rolling(20).mean().iloc[-1])
        result['atr5']  = round(atr5, 2)
        result['atr20'] = round(atr20, 2)
        if atr20 > 0 and atr5 < atr20 * 0.8:
            result['pass']  = True
            result['label'] = f'✅ VCP收縮確認（ATR5={atr5:.2f} < ATR20×0.8={atr20*0.8:.2f}）'
        else:
            result['label'] = f'⏳ 波動未收縮（ATR5={atr5:.2f}，ATR20×0.8={atr20*0.8:.2f}）'
    except Exception:
        result['label'] = '計算失敗'
    return result


# ── 券資比軋空加分 ─────────────────────────────────────────
def calc_short_squeeze_bonus(short_ratio: float = 0.0,
                              inst_consecutive_buy: int = 0) -> dict:
    """
    軋空行情加分：
    條件：券資比 > 30%（short_ratio > 0.3）且 法人連買 ≥ 3 天
    → 總分 +5 分（上限 100）
    short_ratio: 券資比（0~1，如 0.35 代表 35%）
    inst_consecutive_buy: 法人連續買超天數（整數）
    """
    bonus = 0
    label = ''
    if short_ratio > 0.3 and inst_consecutive_buy >= 3:
        bonus = 5
        label = (f'🔥 軋空加分 +5（券資比{short_ratio*100:.0f}%'
                 f' + 法人連買{inst_consecutive_buy}天）')
    elif short_ratio > 0.3:
        label = f'⚠️ 高券資比{short_ratio*100:.0f}%，法人連買天數不足'
    return {'bonus': bonus, 'label': label, 'short_ratio': short_ratio,
            'inst_consecutive_buy': inst_consecutive_buy}


# ════════════════════════════════════════════════════════════
# 模組二：大師級量化選股因子（v3.2 新增）
# ════════════════════════════════════════════════════════════

def check_contract_liability_surge(cl_current, cl_prev_year, paid_in_capital) -> dict:
    """
    合約負債大增檢測（孫慶龍隱形冠軍因子）
    條件：YoY增長>30% 且 合約負債/資本額>10%
    """
    result = {'is_surge': False, 'yoy_pct': None, 'cl_ratio': None, 'label': ''}
    if not cl_current or not cl_prev_year or cl_prev_year <= 0:
        return result
    yoy = (cl_current - cl_prev_year) / cl_prev_year * 100
    ratio = (cl_current / paid_in_capital * 100) if paid_in_capital and paid_in_capital > 0 else 0
    result['yoy_pct'] = round(yoy, 1)
    result['cl_ratio'] = round(ratio, 1)
    if yoy > 30 and ratio > 10:
        result['is_surge'] = True
        result['label'] = '🌟 隱形冠軍潛力（合約負債大增）'
    elif yoy > 15:
        result['label'] = '📈 合約負債成長中'
    return result


def check_bollinger_squeeze(df) -> dict:
    """
    布林帶寬壓縮後爆發（動能發動點）
    條件：今日帶寬>3% 且 前5日平均帶寬<3% 且 收盤>=上軌×0.98
    """
    result = {'is_squeeze_break': False, 'bw_today': None, 'bw_avg5': None, 'label': ''}
    if df is None or len(df) < 25:
        return result
    close = df['close']
    ma20  = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    upper = ma20 + 2 * std20
    lower = ma20 - 2 * std20
    bw = (upper - lower) / ma20 * 100   # 帶寬百分比

    bw_today = float(bw.iloc[-1]) if not bw.iloc[-1] != bw.iloc[-1] else 0
    bw_avg5  = float(bw.iloc[-6:-1].mean()) if len(bw) >= 6 else bw_today

    result['bw_today'] = round(bw_today, 2)
    result['bw_avg5']  = round(bw_avg5, 2)
    result['upper']    = round(float(upper.iloc[-1]), 2)

    close_now = float(close.iloc[-1])
    upper_now = float(upper.iloc[-1])

    if bw_today > 3 and bw_avg5 < 3 and close_now >= upper_now * 0.98:
        result['is_squeeze_break'] = True
        result['label'] = '🚀 布林帶突破—動能發動點'
    elif bw_today < 2:
        result['label'] = '🔵 帶寬收縮中（蓄勢待發）'
    return result


def check_fake_breakout(df) -> dict:
    """
    假突破過濾（爆量長上影線 = 主力出貨）
    條件：成交量>20日均量3倍 且 今日創20日新高 且 收盤<最高-(最高-最低)×0.6
    """
    result = {'is_fake': False, 'label': ''}
    if df is None or len(df) < 21:
        return result
    close  = df['close'].iloc[-1]
    high   = df['high'].iloc[-1]
    low    = df['low'].iloc[-1]
    vol    = df['volume'].iloc[-1]
    avg_v  = df['volume'].rolling(20).mean().iloc[-1]
    hi20   = df['high'].tail(20).max()

    vol_ratio = vol / (avg_v + 1e-10)
    tail_ratio= (high - close) / (high - low + 1e-10)

    if vol_ratio > 3 and high >= hi20 and tail_ratio > 0.6:
        result['is_fake'] = True
        result['label'] = '☠️ 異常量假突破警告（主力出貨）'
    return result


def check_relative_strength(df, df_index=None, days=5) -> dict:
    """
    相對強度：近N日中超過大盤漲幅的天數
    條件：至少3天 個股漲跌幅 > 大盤漲跌幅
    """
    result = {'strong_days': 0, 'is_strong': False, 'label': ''}
    if df is None or len(df) < days + 1:
        return result
    stock_ret = df['close'].pct_change().tail(days)

    if df_index is not None and len(df_index) >= days + 1:
        cc = 'Close' if 'Close' in df_index.columns else 'close'
        idx_ret = df_index[cc].pct_change().tail(days)
        # 對齊日期
        common = min(len(stock_ret), len(idx_ret))
        beats = sum(1 for s, i in zip(stock_ret.tail(common), idx_ret.tail(common)) if s > i)
    else:
        # 無大盤資料：用個股絕對漲幅>0代替
        beats = int((stock_ret > 0).sum())

    result['strong_days'] = beats
    result['is_strong']   = beats >= 3
    result['label'] = f'💪 強勢股（{beats}/{days}天超大盤）' if beats >= 3 else f'弱勢（{beats}/{days}天）'
    return result


def calc_rr_ratio(entry_price, stop_loss, target_price=None) -> dict:
    """
    盈虧比計算（Reward/Risk Ratio）
    目標價 = entry × 1.15（預設+15%）
    盈虧比 < 2 → 模組四：直接剔除不顯示
    """
    if target_price is None:
        target_price = entry_price * 1.15   # 預設目標+15%
    risk   = entry_price - stop_loss
    reward = target_price - entry_price
    if risk <= 0:
        return {'rr': 0, 'pass': False, 'label': '停損設定有誤'}
    rr = round(reward / risk, 2)
    passed = rr >= 2.0
    return {
        'rr': rr,
        'pass': passed,
        'target': round(target_price, 2),
        'risk_amt': round(risk, 2),
        'label': f'盈虧比 {rr:.1f}:1' + ('✅' if passed else ' ❌(<2不顯示)'),
    }


def calculate_position_size(total_capital_twd: float,
                             entry_price: float,
                             atr_value: float,
                             max_risk_pct: float = 0.015) -> dict:
    """
    模組三：動態停損 + 建議買入股數
    Stop_Loss = Entry - 1.5×ATR14
    Max_Risk  = Total_Capital × 1.5%
    Position  = Max_Risk / (Entry - Stop_Loss)

    Args:
        total_capital_twd: 總資金（台幣元）
        entry_price: 進場價（元/股）
        atr_value: ATR14（元）
        max_risk_pct: 單筆最大虧損比例，預設1.5%
    Returns:
        dict: stop_loss/position_size/max_risk/lots
    """
    stop_loss   = round(entry_price - 1.5 * atr_value, 2)
    stop_loss   = max(stop_loss, entry_price * 0.85)  # 最大停損15%保護
    risk_per_sh = entry_price - stop_loss
    if risk_per_sh <= 0:
        return {'error': '停損計算失敗（ATR過大或進場價過低）'}
    max_risk     = total_capital_twd * max_risk_pct
    position_sh  = int(max_risk / risk_per_sh)
    position_lot = position_sh // 1000   # 整張
    position_sh  = position_lot * 1000   # 調整為整張
    cost         = position_sh * entry_price

    # 盈虧比（預設目標+15%）
    rr_info = calc_rr_ratio(entry_price, stop_loss)

    return {
        'stop_loss':    stop_loss,
        'risk_per_sh':  round(risk_per_sh, 2),
        'max_risk':     round(max_risk, 0),
        'position_sh':  position_sh,
        'position_lot': position_lot,
        'cost':         round(cost, 0),
        'rr_ratio':     rr_info['rr'],
        'target_price': rr_info['target'],
        'atr':          round(atr_value, 2),
    }
