"""
v5_modules.py — 台股 AI 戰情室 v5.0 大師滿配版
Tasks: 5=財報領先 6=RS相對強度 7=估值河流圖 8=型態辨識
       9=布林爆發 10=7%存股 11=強制防守 12=動態配置
Author: AI戰情室 v5.0 | 防禦性開發
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple


# ══════════════════════════════════════════════════════════════════════════════
# [Task 5] 財報領先指標 — 合約負債 + 資本支出增速
# ══════════════════════════════════════════════════════════════════════════════
def analyze_fundamental_leading(cl_now: Optional[float], cl_prev: Optional[float],
                                 capex_now: Optional[float], capex_prev: Optional[float],
                                 equity: Optional[float]) -> dict:
    """
    合約負債 YoY 成長 + 資本支出 / 股本比，預判未來 3-6 個月營收動向。

    Args:
        cl_now:    本期合約負債（元）
        cl_prev:   去年同期合約負債（元）
        capex_now: 本期資本支出（元）
        capex_prev:去年同期資本支出
        equity:    股本（元）

    Edge E-C(新股): cl_prev=None → 只做截面分析，不計 YoY
    Edge E-A(API斷): cl_now=None → 回傳 neutral

    Returns: {cl_yoy, capex_ratio, signal, color, msg}
    """
    R = '#da3633'; G = '#2ea043'; Y = '#d29922'; N = '#484f58'

    # Edge: 完全無數據
    if cl_now is None and capex_now is None:
        return {"signal": "⚪ 無財報資料", "color": N,
                "msg": "合約負債與資本支出資料均不可用", "cl_yoy": None, "capex_ratio": None}

    # 合約負債 YoY
    cl_yoy = None
    if cl_now and cl_prev and cl_prev > 0:
        cl_yoy = (cl_now - cl_prev) / cl_prev * 100

    # 資本支出 / 股本比
    capex_ratio = None
    if capex_now and equity and equity > 0:
        capex_ratio = capex_now / equity * 100

    # 訊號邏輯（孫慶龍「龍多股」標準）
    cl_ok     = cl_now and cl_now > 0
    cl_growth = cl_yoy and cl_yoy > 20    # 合約負債 YoY > 20%
    capex_ok  = capex_ratio and capex_ratio > 80  # 資本支出 > 股本 80%

    if cl_growth and capex_ok:
        return {"signal": "🔴 龍多股", "color": R,
                "msg": f"合約負債 YoY +{cl_yoy:.1f}% + 資本支出/股本 {capex_ratio:.0f}% — 未來 3-6 月營收爆發機率高",
                "cl_yoy": round(cl_yoy, 1), "capex_ratio": round(capex_ratio, 1)}
    elif cl_ok and cl_growth:
        return {"signal": "🔴 訂單增加", "color": R,
                "msg": f"合約負債 YoY +{cl_yoy:.1f}% — 手頭訂單充裕，業績有保障",
                "cl_yoy": round(cl_yoy, 1) if cl_yoy else None, "capex_ratio": round(capex_ratio, 1) if capex_ratio else None}
    elif capex_ok:
        return {"signal": "🟡 積極擴張", "color": Y,
                "msg": f"資本支出/股本 {capex_ratio:.0f}% — 積極蓋廠，2年後可能爆發",
                "cl_yoy": round(cl_yoy, 1) if cl_yoy else None, "capex_ratio": round(capex_ratio, 1)}
    else:
        return {"signal": "⚪ 一般水準", "color": N,
                "msg": "合約負債與資本支出未達龍多標準，建議持續觀察",
                "cl_yoy": round(cl_yoy, 1) if cl_yoy else None,
                "capex_ratio": round(capex_ratio, 1) if capex_ratio else None}


# ══════════════════════════════════════════════════════════════════════════════
# [Task 6] RS 相對強度指標
# 公式: RS = (個股同期漲跌幅 - 大盤同期漲跌幅) / 大盤同期波動率
# ══════════════════════════════════════════════════════════════════════════════
def calc_relative_strength(df_stock: pd.DataFrame, df_market: pd.DataFrame,
                            periods: Tuple[int, ...] = (20, 60, 120)) -> dict:
    """
    計算個股相對大盤的超額報酬強度（Z-Score 正規化）。

    Args:
        df_stock:  個股 K 線（含 close 欄）
        df_market: 大盤 K 線（含 close 欄）
        periods:   多週期評估（預設 20/60/120 日）

    Edge E-C(資料不足): 若 len < period → 跳過該週期
    Edge E-B(波動率=0): σ=0 時 RS=0，避免 ZeroDivisionError

    Returns: {rs_scores: {20: 1.23, 60: 0.8, ...}, signal, color, msg}
    """
    R = '#da3633'; G = '#2ea043'; Y = '#d29922'; N = '#484f58'

    def _rs_one(n):
        if len(df_stock) < n or len(df_market) < n:
            return None
        s_ret = (df_stock['close'].iloc[-1] / df_stock['close'].iloc[-n] - 1) * 100
        m_ret = (df_market['close'].iloc[-1] / df_market['close'].iloc[-n] - 1) * 100
        m_std = df_market['close'].pct_change().tail(n).std() * 100
        return round((s_ret - m_ret) / m_std, 2) if m_std > 0.01 else 0.0

    scores = {p: _rs_one(p) for p in periods}
    valid  = [v for v in scores.values() if v is not None]

    if not valid:
        return {"rs_scores": scores, "signal": "⚪ 資料不足", "color": N,
                "avg_rs": None, "msg": "資料不足，無法計算相對強度"}

    avg_rs = round(sum(valid) / len(valid), 2)

    if avg_rs >= 1.0:
        signal, color = "🔴 逆勢強股（領漲）", R
        msg = f"RS均值 +{avg_rs:.2f}σ — 顯著強於大盤，主力護盤意願高"
    elif avg_rs >= 0.3:
        signal, color = "🟡 偏強（溫和抗跌）", Y
        msg = f"RS均值 +{avg_rs:.2f}σ — 略強於大盤，可列觀察清單"
    elif avg_rs >= -0.3:
        signal, color = "⚪ 同步大盤", N
        msg = f"RS均值 {avg_rs:.2f}σ — 與大盤連動，無特別籌碼支撐"
    else:
        signal, color = "🟢 落後大盤（弱勢）", G
        msg = f"RS均值 {avg_rs:.2f}σ — 弱於大盤，空頭環境中優先出清"

    return {"rs_scores": scores, "signal": signal, "color": color,
            "avg_rs": avg_rs, "msg": msg}


# ══════════════════════════════════════════════════════════════════════════════
# [Task 7] 估值河流圖（PE / PB 滾動 μ ± σ 分區）
# ══════════════════════════════════════════════════════════════════════════════
def calc_valuation_zone(price: float, eps_ttm: float, bvps: float,
                         hist_pe_mean: float, hist_pe_std: float,
                         hist_pb_mean: float, hist_pb_std: float) -> dict:
    """
    根據滾動 PE/PB 的歷史均值 ± 標準差，判定現在估值位階。

    區間: 特價(<μ-2σ) | 便宜(μ-2σ~μ-σ) | 合理(μ-σ~μ+σ) | 昂貴(μ+σ~μ+2σ) | 超貴(>μ+2σ)

    Edge E-A(EPS=0負): eps_ttm <= 0 → 改用 PB 評估，跳過 PE
    Edge E-B(歷史不足): hist_std = 0 → 只顯示現值，無法分區
    """
    R = '#da3633'; G = '#2ea043'; Y = '#d29922'; N = '#484f58'; B = '#388bfd'

    result = {"pe": None, "pb": None, "pe_zone": "N/A", "pb_zone": "N/A",
              "signal": "⚪", "color": N, "msg": ""}

    def _zone(val, mu, sigma):
        if sigma < 0.01: return "無歷史基準", N
        if val < mu - 2*sigma: return "🟢便宜（特價）", G
        if val < mu - sigma:   return "🟢便宜", G
        if val < mu + sigma:   return "⚪合理", N
        if val < mu + 2*sigma: return "🔴昂貴", R
        return "🔴超貴", R

    # PE 評估
    if eps_ttm and eps_ttm > 0 and price > 0:
        pe = round(price / eps_ttm, 1)
        pe_zone, pe_color = _zone(pe, hist_pe_mean, hist_pe_std)
        result.update({"pe": pe, "pe_zone": pe_zone})
    else:
        pe_color = N; pe_zone = "EPS<0（虧損）"
        result.update({"pe": None, "pe_zone": pe_zone})

    # PB 評估
    if bvps and bvps > 0 and price > 0:
        pb = round(price / bvps, 2)
        pb_zone, pb_color = _zone(pb, hist_pb_mean, hist_pb_std)
        result.update({"pb": pb, "pb_zone": pb_zone})
    else:
        pb_color = N; pb_zone = "無資料"
        result.update({"pb": None, "pb_zone": pb_zone})

    # 綜合訊號（PE 優先，PB 備援）
    primary_color = pe_color if result['pe'] else pb_color
    primary_zone  = pe_zone  if result['pe'] else pb_zone

    if "便宜" in primary_zone or "特價" in primary_zone:
        result.update({"signal": "🟢 估值便宜", "color": G,
                        "msg": f"PE={result['pe']} 位於{primary_zone} — 估值具吸引力，可分批布局"})
    elif "昂貴" in primary_zone or "超貴" in primary_zone:
        result.update({"signal": "🔴 估值昂貴", "color": R,
                        "msg": f"PE={result['pe']} 位於{primary_zone} — 估值偏高，追高風險大"})
    else:
        result.update({"signal": "⚪ 估值合理", "color": N,
                        "msg": f"PE={result['pe']} 位於合理區間 — 可持有，等候更好買點"})
    return result


# ══════════════════════════════════════════════════════════════════════════════
# [Task 9] 布林帶寬爆發偵測
# 公式: BW = (Upper - Lower) / MA20 × 100%
# ══════════════════════════════════════════════════════════════════════════════
def detect_bollinger_breakout(df: pd.DataFrame, window: int = 20, std_k: float = 2.0) -> dict:
    """
    計算布林帶寬 BW，偵測「極度收縮」(窒息量前兆) 與「突破上軌」訊號。

    Args:
        df: K 線（含 close 與 volume 欄）
        window: MA 週期，預設 20
        std_k:  帶寬倍數，預設 2σ

    Edge E-C(資料<20): 直接回傳警示
    Edge E-B(std=0): close 全相同（停牌），回傳中性

    Returns: {bw, bw_pct, upper, lower, ma, signal, color, msg}
    """
    R = '#da3633'; G = '#2ea043'; Y = '#d29922'; N = '#484f58'

    if len(df) < window:
        return {"bw": None, "signal": "⚪ 資料不足", "color": N,
                "msg": f"需至少 {window} 根 K 線，目前僅 {len(df)} 根"}

    close = df['close'].ffill().fillna(method='bfill')
    ma    = close.rolling(window).mean()
    std   = close.rolling(window).std()

    ma_now  = float(ma.iloc[-1])
    std_now = float(std.iloc[-1])

    if std_now < 0.001 or ma_now < 0.001:
        return {"bw": 0, "signal": "⚪ 停牌/無波動", "color": N, "msg": "價格無波動（疑似停牌）"}

    upper = ma_now + std_k * std_now
    lower = ma_now - std_k * std_now
    bw    = round((upper - lower) / ma_now * 100, 2)
    close_now = float(close.iloc[-1])

    # 歷史 BW 百分位（近 120 日）
    bw_hist = ((ma + std_k*std) - (ma - std_k*std)) / ma * 100
    bw_pct  = round(float((bw_hist.tail(120) < bw).mean() * 100), 1)

    # 訊號判斷
    near_upper = close_now >= upper * 0.995
    bw_squeeze = bw_pct < 20  # 帶寬在近120日最低20%

    if near_upper and bw > 3:
        signal, color = "🔴 布林突破爆發", R
        msg = f"BW={bw:.1f}% 且收盤 {close_now:.2f} 貼近上軌 {upper:.2f} — 短線爆發買點"
    elif bw_squeeze:
        signal, color = "🟡 布林極度收縮", Y
        msg = f"BW={bw:.1f}%（近120日第{bw_pct:.0f}百分位）— 窒息量前兆，方向選擇即將到來"
    elif near_upper:
        signal, color = "🟡 靠近上軌", Y
        msg = f"收盤 {close_now:.2f} 靠近布林上軌 {upper:.2f}，注意短線壓力"
    else:
        signal, color = "⚪ 帶寬正常", N
        msg = f"BW={bw:.1f}%，帶寬正常，無特殊訊號"

    return {"bw": bw, "bw_pct": bw_pct, "upper": round(upper, 2),
            "lower": round(lower, 2), "ma": round(ma_now, 2),
            "close": close_now, "near_upper": near_upper,
            "signal": signal, "color": color, "msg": msg}


# ══════════════════════════════════════════════════════════════════════════════
# [Task 10] 7% 存股殖利率評估（孫慶龍 357 聖經）
# 公式: Y_est = EPS_4Q × PayoutRatio_3Y / Price × 100%
# ══════════════════════════════════════════════════════════════════════════════
def calc_dividend_yield_357(price: float, eps_ttm: float,
                             avg_payout: float, div_years: int,
                             hist_div: Optional[list] = None) -> dict:
    """
    預估存股殖利率 + 357 位階判定。

    Args:
        price:       現價
        eps_ttm:     近四季 EPS 合計
        avg_payout:  近三年平均配發率（0~1）
        div_years:   連續配息年數
        hist_div:    歷史配息記錄（元/年，list 近到遠）

    Edge E-A(EPS<0):  無法估算，回傳警示
    Edge E-A(Price=0): ZeroDivisionError 防禦

    Returns: {est_yield, zone_357, signal, color, p_cheap, p_fair, p_expensive, msg}
    """
    R = '#da3633'; G = '#2ea043'; Y = '#d29922'; N = '#484f58'

    if not price or price <= 0:
        return {"est_yield": None, "signal": "⚪ 無股價", "color": N, "msg": "無法取得股價"}

    if not eps_ttm or eps_ttm <= 0:
        return {"est_yield": None, "signal": "⚪ EPS≤0", "color": N,
                "msg": "近四季 EPS 為負或零，不適用殖利率法則"}

    # 估算股利
    est_div = eps_ttm * max(min(avg_payout, 1.0), 0.0)
    est_yield = round(est_div / price * 100, 2)

    # 357 價位計算（以估算股利反推）
    p_cheap    = round(est_div / 0.07, 1)  # 7% → 便宜
    p_fair     = round(est_div / 0.05, 1)  # 5% → 合理
    p_expensive= round(est_div / 0.03, 1)  # 3% → 昂貴

    # 連續配息加分
    stable = div_years >= 5

    if est_yield >= 7 and stable:
        signal, color = "🟢 甜甜價（7%+連續5年）", G
        msg = f"預估殖利率 {est_yield:.2f}% ≥ 7% 且連續配息 {div_years} 年 — 孫慶龍存股首選"
    elif est_yield >= 7:
        signal, color = "🟢 高殖利率（配息不穩定）", G
        msg = f"殖利率 {est_yield:.2f}% 高，但連續配息僅 {div_years} 年（<5年），需確認配息穩定性"
    elif est_yield >= 5:
        signal, color = "🟡 合理（5~7%）", Y
        msg = f"預估殖利率 {est_yield:.2f}%，位於合理區間，可分批布局"
    elif est_yield >= 3:
        signal, color = "🔴 昂貴（3~5%）", R
        msg = f"預估殖利率 {est_yield:.2f}%，位於昂貴區，持有但不追高"
    else:
        signal, color = "🔴 超貴（<3%）", R
        msg = f"預估殖利率僅 {est_yield:.2f}%，估值過高，建議逢高減碼"

    return {
        "est_yield": est_yield, "est_div": round(est_div, 2),
        "p_cheap": p_cheap, "p_fair": p_fair, "p_expensive": p_expensive,
        "div_years": div_years, "signal": signal, "color": color, "msg": msg,
    }


# ══════════════════════════════════════════════════════════════════════════════
# [Task 12] 動態資產配置建議
# 總經紅燈 → 建議防禦型 ETF 停泊資金
# ══════════════════════════════════════════════════════════════════════════════
DEFENSIVE_ETFS = {
    "00679B": {"name": "元大美債 20年", "type": "長天期美債", "note": "總經高風險首選避風港"},
    "00720B": {"name": "元大投資級債",  "type": "投資級公司債", "note": "中度風險緩衝"},
    "00878":  {"name": "國泰永續高股息","type": "高息防禦股", "note": "景氣下行仍有配息"},
    "006208": {"name": "富邦台50",      "type": "大型權值ETF", "note": "黃燈時降低個股風險"},
}

def get_defensive_allocation(macro_level: str) -> dict:
    """
    依總經燈號給出資金停泊建議。

    Args:
        macro_level: 'High Risk' / 'Medium Risk' / 'Safe'

    Returns: {allocation, etf_recommendations, msg}
    """
    if macro_level == "High Risk":
        return {
            "stock_pct": 20, "bond_pct": 60, "cash_pct": 20,
            "etf_recommendations": ["00679B", "00720B"],
            "msg": "🚨 總經紅燈：建議股票部位降至 20%，60% 轉入長天期美債 ETF（00679B）停泊，20% 保留現金備戰"
        }
    elif macro_level == "Medium Risk":
        return {
            "stock_pct": 50, "bond_pct": 30, "cash_pct": 20,
            "etf_recommendations": ["00720B", "006208"],
            "msg": "⚠️ 總經黃燈：股票降至 50%，30% 轉入投資級債 ETF，20% 現金等候回補機會"
        }
    else:
        return {
            "stock_pct": 80, "bond_pct": 10, "cash_pct": 10,
            "etf_recommendations": [],
            "msg": "✅ 總經安全：可積極佈局，維持 80% 股票部位，10% 債券避險，10% 現金備戰"
        }


# ══════════════════════════════════════════════════════════════════════════════
# [Step 6] 自動化邊界測試
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("v5_modules.py 自動化邊界測試")
    print("=" * 60)

    import traceback

    # ── Task 5: 財報領先
    print("\n[Task 5] 財報領先指標")
    try:
        r = analyze_fundamental_leading(5e9, 2e9, 8e9, 3e9, 10e9)
        print(f"  {r['signal']}: {r['msg'][:50]}  ✅")
        r2 = analyze_fundamental_leading(None, None, None, None, None)
        assert r2['cl_yoy'] is None
        print(f"  無資料防禦: {r2['signal']}  ✅")
    except Exception as e:
        print(f"  ❌ {e}"); traceback.print_exc()

    # ── Task 6: RS 相對強度
    print("\n[Task 6] RS 相對強度")
    try:
        dates = pd.date_range('2024-01-01', periods=150)
        df_s = pd.DataFrame({'close': 100 * (1 + np.random.randn(150).cumsum()*0.01)}, index=dates)
        df_m = pd.DataFrame({'close':  50 * (1 + np.random.randn(150).cumsum()*0.01)}, index=dates)
        r = calc_relative_strength(df_s, df_m)
        print(f"  {r['signal']}: RS={r['avg_rs']}  ✅")
        # 邊界：資料不足
        r2 = calc_relative_strength(df_s.head(5), df_m)
        print(f"  資料不足防禦: {r2['signal']}  ✅")
    except Exception as e:
        print(f"  ❌ {e}"); traceback.print_exc()

    # ── Task 7: 估值河流圖
    print("\n[Task 7] 估值河流圖")
    try:
        r = calc_valuation_zone(100, 8, 60, 12, 3, 1.5, 0.3)
        print(f"  {r['signal']}: PE={r['pe']}  ✅")
        r2 = calc_valuation_zone(100, -1, 60, 12, 3, 1.5, 0.3)
        assert r2['pe'] is None
        print(f"  EPS<0防禦: pe={r2['pe']}  ✅")
    except Exception as e:
        print(f"  ❌ {e}"); traceback.print_exc()

    # ── Task 9: 布林爆發
    print("\n[Task 9] 布林帶寬偵測")
    try:
        df_bb = pd.DataFrame({'close': [100]*15 + list(100+np.random.randn(25)*2),
                              'volume': np.random.randint(1000, 5000, 40)})
        r = detect_bollinger_breakout(df_bb)
        print(f"  {r['signal']}: BW={r['bw']}%  ✅")
        r2 = detect_bollinger_breakout(df_bb.head(5))
        print(f"  資料不足防禦: {r2['signal']}  ✅")
    except Exception as e:
        print(f"  ❌ {e}"); traceback.print_exc()

    # ── Task 10: 存股殖利率
    print("\n[Task 10] 7% 存股殖利率")
    try:
        r = calc_dividend_yield_357(100, 8, 0.75, 7)
        print(f"  {r['signal']}: Y={r['est_yield']}%  ✅")
        r2 = calc_dividend_yield_357(0, 8, 0.75, 5)
        print(f"  Price=0防禦: {r2['signal']}  ✅")
        r3 = calc_dividend_yield_357(100, -1, 0.75, 3)
        print(f"  EPS<0防禦: {r3['signal']}  ✅")
    except Exception as e:
        print(f"  ❌ {e}"); traceback.print_exc()

    # ── Task 12: 動態配置
    print("\n[Task 12] 動態資產配置")
    try:
        for level in ["High Risk", "Medium Risk", "Safe"]:
            r = get_defensive_allocation(level)
            print(f"  {level}: 股{r['stock_pct']}%/債{r['bond_pct']}%  ✅")
    except Exception as e:
        print(f"  ❌ {e}"); traceback.print_exc()

    print("\n" + "=" * 60)
    print("v5_modules 邊界測試完成")
    print("=" * 60)
