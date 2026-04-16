"""
市場狀態判斷引擎 v4.0 (§5.1)
目的：先判斷是否適合積極進場
輸出：bull / neutral / bear + 建議持股比例
v4.0 新增：宏爺 M1B-M2 資金活水評分維度
"""
import requests
import datetime
try:
    from config import (MARKET_SCORE_BULL, MARKET_SCORE_NEUTRAL,
                        EXPOSURE_BULL, EXPOSURE_NEUTRAL, EXPOSURE_BEAR)
except ImportError:
    MARKET_SCORE_BULL = 3; MARKET_SCORE_NEUTRAL = 2
    EXPOSURE_BULL = 0.8; EXPOSURE_NEUTRAL = 0.5; EXPOSURE_BEAR = 0.2


# ── 外部資料抓取 ──────────────────────────────────────────────
def fetch_market_data():
    """從 TWSE 取得大盤外資法人淨買賣（備援用）"""
    today = datetime.date.today()
    for delta in range(7):
        d = today - datetime.timedelta(days=delta)
        if d.weekday() < 5:
            date_str = d.strftime('%Y%m%d')
            break
    try:
        r = requests.get(
            'https://www.twse.com.tw/fund/BFI82U',
            params={'response': 'json', 'dayDate': date_str},
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=10
        )
        data = r.json()
        if data.get('stat') == 'OK' and data.get('data'):
            foreign_net = 0
            for row in data['data']:
                if '外資' in row[0] and '自營' not in row[0]:
                    buy  = float(str(row[1]).replace(',', '') or 0)
                    sell = float(str(row[2]).replace(',', '') or 0)
                    foreign_net = buy - sell
            return {'foreign_net': foreign_net, 'date': date_str}
    except Exception as e:
        print(f'[MarketStrategy] TWSE 法人數據失敗: {e}')
    return {'foreign_net': None, 'date': ''}  # None 表示資料取得失敗，非「零」


# ── 核心：市場狀態判斷 (§5.1) ─────────────────────────────────
def market_regime(index_close, ma60, ma120, foreign_buy, ad_ratio=1.0,
                  ma60_prev=None, ma120_prev=None, vol_today=0, avg_vol_20=1,
                  m1b_m2_gap=None, m1b_m2_prev=None):
    """
    市場狀態判斷引擎 v4.0
    新增：MA斜率過濾（防假突破）+ 瘋牛濾網 + 宏爺 M1B-M2 資金活水評分

    m1b_m2_gap:  float | None — M1B年增率 - M2年增率（百分點）
    m1b_m2_prev: float | None — 上月 gap，用於判斷趨勢方向
    """
    score = 0
    signals = []

    # ① 站上 MA60（+均線向上斜率過濾）
    if index_close > ma60:
        score += 1
        signals.append('✅ 站上MA60')
        if ma60_prev and ma60 > ma60_prev:
            score += 0.5
            signals.append('✅ MA60向上彎折（真突破濾網）')
        elif ma60_prev and ma60 < ma60_prev:
            signals.append('⚠️ MA60仍向下（可能假突破）')
    else:
        signals.append('❌ 跌破MA60')

    # ② 站上 MA120（+均線斜率）
    if index_close > ma120:
        score += 1
        signals.append('✅ 站上MA120')
        if ma120_prev and ma120 > ma120_prev:
            score += 0.5
            signals.append('✅ MA120向上彎折')
    else:
        signals.append('❌ 跌破MA120')

    # ③ 外資方向
    if foreign_buy is None or foreign_buy == 0:
        signals.append('⏰ 外資數據待更新（收盤後15:30可用）')
    elif foreign_buy > 0:
        score += 1
        signals.append(f'✅ 外資買超 {foreign_buy/1e8:.1f}億')
    else:
        signals.append(f'❌ 外資賣超 {abs(foreign_buy)/1e8:.1f}億')

    # ④ 市場廣度
    if ad_ratio > 1.0:
        score += 1
        signals.append(f'✅ 市場廣度正向 ({ad_ratio:.2f})')
    else:
        signals.append(f'❌ 市場廣度偏弱 ({ad_ratio:.2f})')

    # ⑤ 宏爺 M1B-M2 資金活水（選填，不傳則略過，向後相容）
    if m1b_m2_gap is not None:
        _trending_up = (m1b_m2_prev is not None) and (m1b_m2_gap > m1b_m2_prev)
        if m1b_m2_gap > 0 and _trending_up:
            score += 1
            signals.append(f'💧 M1B-M2 活水正向且上升 ({m1b_m2_gap:+.2f}%)')
        elif m1b_m2_gap > 0:
            score += 0.5
            signals.append(f'💧 M1B-M2 活水正向 ({m1b_m2_gap:+.2f}%)，趨勢待確認')
        else:
            signals.append(f'🚱 M1B-M2 資金動能偏弱 ({m1b_m2_gap:+.2f}%)，延後積極進場')

    # ── 判定 regime
    _bull_threshold   = 3
    _neutral_threshold = 2
    if score >= _bull_threshold:
        regime = 'bull'
    elif score >= _neutral_threshold:
        regime = 'neutral'
    else:
        regime = 'bear'

    # ── 瘋牛濾網
    _bullrun = vol_today > avg_vol_20 * 1.3 if avg_vol_20 > 0 else False
    if _bullrun:
        signals.append(f'💹 瘋牛模式：成交量 {vol_today/avg_vol_20:.1f}x 均量')

    # max_score：基礎 5 分（MA×2 + 外資 + 廣度 + 斜率×1）+ M1B-M2 最多 1 分 = 6
    _max = 6 if m1b_m2_gap is not None else 5

    return {
        'regime': regime,
        'bullrun': _bullrun,
        'score': score,
        'max_score': _max,
        'signals': signals,
        'label': {'bull': '🟢 多頭', 'neutral': '🟡 中性', 'bear': '🔴 空頭'}[regime],
        'm1b_m2_gap': m1b_m2_gap,
    }


def portfolio_exposure(regime: str) -> float:
    """
    依市場狀態決定建議總持股比例（§6.3）

    bull    → 80%（積極）
    neutral → 50%（保守）
    bear    → 20%（觀望，降至30%以下）
    """
    mapping = {
        'bull':    EXPOSURE_BULL,
        'neutral': EXPOSURE_NEUTRAL,
        'bear':    EXPOSURE_BEAR,
    }
    return mapping.get(regime, EXPOSURE_NEUTRAL)


# ── 舊版評分（已棄用，僅保留相容性，新版請使用 market_regime）───
def market_score(index_price, ma200, foreign_buy, volume, avg_volume=1000):
    """舊版市場評分（MA200 年線 + 外資 + 量能），保留相容性"""
    score = 0; signals = []
    if index_price > ma200:
        score += 2; signals.append('✅ 站上年線 (+2)')
    else:
        signals.append('❌ 跌破年線 (0)')
    _fb_bn = round(foreign_buy / 1e8, 1) if abs(foreign_buy) > 1e6 else foreign_buy
    if foreign_buy > 0:
        score += 2; signals.append(f'✅ 外資買超 {_fb_bn:+.1f}億 (+2)')
    else:
        signals.append(f'❌ 外資賣超 {abs(_fb_bn):.1f}億 (0)')
    _vol_ratio = round(volume / avg_volume, 2) if avg_volume > 0 else 1
    if volume > avg_volume:
        score += 1; signals.append(f'✅ 量能放大 {_vol_ratio:.1f}x (+1)')
    else:
        signals.append(f'⚠️ 量能萎縮 {_vol_ratio:.1f}x (0)')
    status = '多頭' if score >= 4 else ('盤整' if score >= 2 else '空頭')
    confidence = min(100, score * 20) if score >= 4 else (score * 15 if score >= 2 else max(0, 30 - score*10))
    return {'score': score, 'max_score': 5, 'status': status,
            'confidence': confidence, 'signals': signals}


def get_market_assessment(df_index=None, foreign_net=None,
                          m1b_m2_gap=None, m1b_m2_prev=None):
    """
    整合版市場評估（v4.0 升級版）
    同時輸出 regime (bull/neutral/bear) 與舊版 score
    m1b_m2_gap:  M1B年增率 - M2年增率（百分點）；None = 不納入評分
    m1b_m2_prev: 上月 gap，用於判斷趨勢方向
    """
    import yfinance as yf
    if df_index is None:
        try:
            tw = yf.Ticker('^TWII')
            df_index = tw.history(period='300d')[['Close', 'Volume']]
        except Exception as e:
            print(f'[MarketStrategy] 大盤數據失敗: {e}')
            return None

    if df_index is None or df_index.empty:
        return None

    # 支援大小寫欄位（fetch_single 回傳小寫，yfinance 直接回傳大寫）
    _df = df_index.copy()
    if 'close' in _df.columns and 'Close' not in _df.columns:
        _df = _df.rename(columns={'close':'Close','open':'Open','high':'High','low':'Low','volume':'Volume'})
    if 'Close' not in _df.columns:
        return None
    df_index = _df

    current_price = float(df_index['Close'].iloc[-1])
    ma60  = float(df_index['Close'].rolling(60).mean().iloc[-1])  if len(df_index) >= 60  else current_price
    ma120 = float(df_index['Close'].rolling(120).mean().iloc[-1]) if len(df_index) >= 120 else current_price
    ma200 = float(df_index['Close'].rolling(200).mean().iloc[-1]) if len(df_index) >= 200 else current_price
    avg_vol   = float(df_index['Volume'].rolling(20).mean().iloc[-1]) if 'Volume' in df_index.columns else 1000
    vol_today = float(df_index['Volume'].iloc[-1]) if 'Volume' in df_index.columns else avg_vol

    if foreign_net is None:
        mkt = fetch_market_data()
        foreign_net = mkt.get('foreign_net') or 0  # None(API失敗) → 0 避免 TypeError

    # P9修正: 傳入前一日MA值，讓斜率過濾生效
    ma60_prev  = float(df_index['Close'].rolling(60).mean().iloc[-2])  if len(df_index) >= 61 else None
    ma120_prev = float(df_index['Close'].rolling(120).mean().iloc[-2]) if len(df_index) >= 121 else None
    regime_result = market_regime(current_price, ma60, ma120, foreign_net,
                                  ma60_prev=ma60_prev, ma120_prev=ma120_prev,
                                  vol_today=vol_today, avg_vol_20=avg_vol,
                                  m1b_m2_gap=m1b_m2_gap, m1b_m2_prev=m1b_m2_prev)
    old_result    = market_score(current_price, ma200, foreign_net, vol_today, avg_vol)

    # P5修正: 保留新版signals，不讓old_result.signals覆蓋
    result = {**old_result, **regime_result}   # regime優先
    result['signals'] = regime_result.get('signals', [])  # 確保新版signals不被覆蓋
    result['index_price'] = round(current_price, 2)
    result['ma60']  = round(ma60, 2)
    result['ma120'] = round(ma120, 2)
    result['ma200'] = round(ma200, 2)
    result['foreign_net']   = foreign_net
    result['exposure']      = portfolio_exposure(regime_result['regime'])
    result['exposure_pct']  = f"{portfolio_exposure(regime_result['regime'])*100:.0f}%"
    return result
