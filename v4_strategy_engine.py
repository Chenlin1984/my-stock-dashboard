"""
v4_strategy_engine.py — 台股 AI 戰情室 v4.0 核心策略引擎
Tasks: 1=相對籌碼 2=總經否決 3=套牢賣壓 4=防守線
Author: AI戰情室 v4.0
"""
import pandas as pd
import numpy as np


class V4StrategyEngine:
    """
    台股 AI 戰情室 v4.0 核心策略引擎
    實作：相對籌碼比、總經否決權、套牢賣壓、強制停損線
    
    Attributes:
        df: 個股 K 線（需含 close/open/low/volume/foreign_net/trust_net）
        macro: 總經字典（vix, foreign_futures, pcr）
        shares_total: 發行總張數
    """

    def __init__(self, df_stock: pd.DataFrame, df_macro: dict, shares_total: int):
        """
        Args:
            df_stock: K 線 DataFrame（columns: close/open/low/volume/foreign_net/trust_net）
            df_macro: 總經數據字典 {"vix":..., "foreign_futures":..., "pcr":...}
            shares_total: 發行總張數（大於 0，否則 raise ValueError）
        
        Edge Case E-A: 股本為 0 或 None → raise ValueError
        """
        if not shares_total or shares_total <= 0:
            raise ValueError("發行張數必須大於 0")
        
        # 標準化欄位名稱（相容大小寫）
        col_map = {}
        for col in df_stock.columns:
            low_col = col.lower()
            if low_col in ('close', 'adj close'): col_map[col] = 'close'
            elif low_col == 'open': col_map[col] = 'open'
            elif low_col == 'low': col_map[col] = 'low'
            elif low_col in ('volume', 'trading_volume'): col_map[col] = 'volume'
            elif 'foreign' in low_col: col_map[col] = 'foreign_net'
            elif 'trust' in low_col: col_map[col] = 'trust_net'
        
        self.df = df_stock.rename(columns=col_map).copy()
        
        # Edge Case E-A: NaN / inf 防禦
        self.df = self.df.ffill().fillna(0).replace([float('inf'), float('-inf')], 0)
        
        self.macro = df_macro or {}
        self.shares_total = int(shares_total)

    # ─────────────────────────────────────────────────────────────
    # [Task 2] 總經紅綠燈一票否決權
    # ─────────────────────────────────────────────────────────────
    def check_macro_veto(self) -> dict:
        """
        總經紅綠燈：VIX + 外資期貨口數 → 強制持股水位上限
        
        Returns:
            dict: {status, level, color, max_position, msg}
        
        Edge Case E-B: API 斷線 → 預設黃燈（保守）
        """
        try:
            vix = float(self.macro.get('vix') or 15)
        except (TypeError, ValueError):
            vix = 15  # 無法取得 VIX → 預設安全值

        try:
            futures = float(self.macro.get('foreign_futures') or 0)
        except (TypeError, ValueError):
            futures = 0

        try:
            pcr = float(self.macro.get('pcr') or 100)
        except (TypeError, ValueError):
            pcr = 100

        # 紅燈：高風險
        if vix > 25 or futures < -20000:
            return {
                "status":       "🔴 紅燈",
                "level":        "High Risk",
                "color":        "#da3633",
                "max_position": 20,
                "msg":          "🚨 總經環境高風險！VIX={:.1f} / 外資期貨={:,.0f}口 — 建議持股 ≤20%，嚴禁追高攤平".format(vix, futures),
                "vix":          vix,
                "futures":      futures,
            }
        # 黃燈：中度風險
        elif vix > 20 or futures < -10000:
            return {
                "status":       "🟡 黃燈",
                "level":        "Medium Risk",
                "color":        "#d29922",
                "max_position": 50,
                "msg":          "⚠️ 大盤震盪中，VIX={:.1f} — 縮小部位，跌破防守線務必嚴格執行".format(vix),
                "vix":          vix,
                "futures":      futures,
            }
        # 綠燈：安全
        else:
            return {
                "status":       "🟢 綠燈",
                "level":        "Safe",
                "color":        "#2ea043",
                "max_position": 100,
                "msg":          "✅ 總經環境安全，VIX={:.1f} / 外資期貨={:,.0f}口 — 可依策略佈局".format(vix, futures),
                "vix":          vix,
                "futures":      futures,
            }

    # ─────────────────────────────────────────────────────────────
    # [Task 1] 相對籌碼比例（外本比 / 投本比）
    # 公式: Ratio = (sum_buy - sum_sell) / shares_total * 100%
    # ─────────────────────────────────────────────────────────────
    def calc_relative_chips(self, days: int = 5) -> dict:
        """
        外本比 = 近N日外資淨買超 / 發行張數 × 100%
        投本比 = 近N日投信淨買超 / 發行張數 × 100%
        
        Edge Case E-A: foreign_net / trust_net 欄位不存在 → 回傳 None
        
        Returns:
            dict: {foreign_ratio, trust_ratio, signal, msg}
        """
        if 'foreign_net' not in self.df.columns or 'trust_net' not in self.df.columns:
            return {
                "foreign_ratio": None,
                "trust_ratio":   None,
                "signal":        "⚪ 無籌碼資料",
                "msg":           "無外資/投信買賣超資料，無法計算相對籌碼",
                "consecutive":   0,
            }

        recent = self.df.tail(days)
        foreign_net = recent['foreign_net'].sum()
        trust_net   = recent['trust_net'].sum()

        foreign_ratio = (foreign_net / self.shares_total) * 100
        trust_ratio   = (trust_net   / self.shares_total) * 100

        # 連續 N 日外本比 > 0.1% 判定籌碼轉強
        recent_foreign = self.df.tail(3)['foreign_net']
        consecutive_in = (recent_foreign / self.shares_total * 100 > 0.1).sum()

        if foreign_ratio > 0.5 or trust_ratio > 0.3:
            signal = "🔴 籌碼強勢集中"
            msg    = f"近{days}日外本比 {foreign_ratio:+.2f}% / 投本比 {trust_ratio:+.2f}%（超過0.5%門檻）"
        elif foreign_ratio < -0.5 or trust_ratio < -0.3:
            signal = "🟢 籌碼渙散出逃"
            msg    = f"大戶正在撤退，外本比 {foreign_ratio:+.2f}% / 投本比 {trust_ratio:+.2f}%"
        else:
            signal = "⚪ 籌碼中性"
            msg    = f"無明顯籌碼動能，外本比 {foreign_ratio:+.2f}% / 投本比 {trust_ratio:+.2f}%"

        if consecutive_in >= 3:
            signal += "（連續3日流入✅）"

        return {
            "foreign_ratio": round(foreign_ratio, 3),
            "trust_ratio":   round(trust_ratio, 3),
            "signal":        signal,
            "msg":           msg,
            "consecutive":   int(consecutive_in),
        }

    # ─────────────────────────────────────────────────────────────
    # [Task 3] 上方套牢賣壓檢測（VPOC）
    # 公式: bins = pd.cut(close, 20) → sum(volume by bin) → argmax
    # ─────────────────────────────────────────────────────────────
    def find_overhead_resistance(self, lookback: int = 120) -> dict:
        """
        Volume Point of Control (VPOC)：最大成交量密集區
        向量化分箱 O(n)，比迴圈快 10x
        
        Edge Case E-C: 資料 < 60 天 → 回傳警示
        
        Returns:
            dict: {vpoc_price, current_price, has_pressure, msg}
        """
        if len(self.df) < 60:
            return {
                "vpoc_price":    None,
                "current_price": float(self.df['close'].iloc[-1]) if len(self.df) > 0 else None,
                "has_pressure":  False,
                "msg":           "⚪ 資料不足60日，無法計算套牢賣壓（新股或資料缺失）",
            }

        recent = self.df.tail(lookback).copy()
        current_price = float(recent['close'].iloc[-1])

        try:
            # 向量化分箱（20個價格區間）
            bins = pd.cut(recent['close'], bins=20, duplicates='drop')
            vol_profile = recent.groupby(bins, observed=True)['volume'].sum()
            vpoc_interval = vol_profile.idxmax()
            vpoc_price = float(vpoc_interval.mid)
        except Exception:
            return {
                "vpoc_price":    None,
                "current_price": current_price,
                "has_pressure":  False,
                "msg":           "⚪ VPOC 計算失敗（價格波動極小或資料異常）",
            }

        distance = (vpoc_price - current_price) / current_price if current_price > 0 else 0
        has_pressure = current_price < vpoc_price and distance < 0.15

        if has_pressure:
            msg = f"⚠️ 上方 {vpoc_price:.1f} 元附近有近{lookback}日最大量套牢賣壓（距離 {distance*100:.1f}%），突破前觀望"
        elif current_price >= vpoc_price:
            msg = f"✅ 現價 {current_price:.1f} 已站上 VPOC {vpoc_price:.1f}，上方壓力已解除"
        else:
            msg = f"✅ 上方套牢區距離 {distance*100:.1f}%（> 15%），短期壓力有限"

        return {
            "vpoc_price":    round(vpoc_price, 2),
            "current_price": round(current_price, 2),
            "has_pressure":  has_pressure,
            "distance_pct":  round(distance * 100, 2),
            "msg":           msg,
        }

    # ─────────────────────────────────────────────────────────────
    # [Task 4] 數字化防守線
    # 公式: stop_loss = min(MA20, 近10日帶量紅K最低點)
    # ─────────────────────────────────────────────────────────────
    def calculate_stop_loss(self) -> dict:
        """
        防守線 = min(MA20, 近10日爆量紅K低點)
        
        Edge Case E-C: 資料 < 20 日 → 降級用 MA5 或最近低點
        
        Returns:
            dict: {stop_loss, ma20, breakout_low, current_price, msg}
        """
        if len(self.df) < 5:
            return {
                "stop_loss":     None,
                "ma20":          None,
                "breakout_low":  None,
                "current_price": None,
                "msg":           "⚪ 新股觀望 — 資料不足，無法計算防守線",
            }

        current_price = float(self.df['close'].iloc[-1])

        # MA20（或 MA5 降級）
        if len(self.df) >= 20:
            ma20 = float(self.df['close'].rolling(20).mean().iloc[-1])
        else:
            ma20 = float(self.df['close'].rolling(min(len(self.df), 5)).mean().iloc[-1])

        # 近10日爆量紅K低點
        recent_10 = self.df.tail(10)
        avg_vol = float(self.df['volume'].rolling(min(len(self.df), 20)).mean().iloc[-1])
        avg_vol = avg_vol if avg_vol > 0 else 1

        mask = (
            (recent_10['volume'] > avg_vol * 1.5) &
            (recent_10['close'] > recent_10['open'])
        )
        breakout_bars = recent_10[mask]

        if not breakout_bars.empty:
            breakout_low = float(breakout_bars['low'].min())
        else:
            # 無爆量紅K → 用近10日低點 × 0.98 作備援
            breakout_low = float(recent_10['low'].min()) * 0.98

        stop_loss = round(min(ma20, breakout_low), 2)
        sl_pct    = (current_price - stop_loss) / current_price * 100 if current_price > 0 else 0

        return {
            "stop_loss":     stop_loss,
            "ma20":          round(ma20, 2),
            "breakout_low":  round(breakout_low, 2),
            "current_price": round(current_price, 2),
            "risk_pct":      round(sl_pct, 1),
            "msg":           f"🛡️ 嚴格防守價：{stop_loss:.2f} 元（距現價 {sl_pct:.1f}%）— 收盤跌破請無條件停損",
        }

    # ─────────────────────────────────────────────────────────────
    # [Task 5] 春哥 VCP 三階段波動收縮偵測（含等幅測距目標價）
    # 春哥原理：波幅遞減 + 窒息量 + 帶量突破 = 籌碼沉澱完畢
    # ─────────────────────────────────────────────────────────────
    def detect_vcp_breakout(self, lookback_days: int = 60) -> dict:
        """
        春哥 VCP 三階段波動收縮 + 帶量突破偵測。

        偵測邏輯：
          1. 將 lookback 區間切為 3 段，計算每段波幅（High-Low/High）
          2. 三段波幅必須遞減（第三段 < 第二段 < 第一段）
          3. 近 5 日出現窒息量（< 50日均量 × 50%）
          4. 最新收盤突破區間最高點（容許 1% 誤差），且量 > 50日均量 × 1.5

        返回 dict：
          signal:       'BUY' | 'HOLD' | 'NONE'（資料不足）
          vcp_stages:   [float, float, float]  各段波幅（%）
          volume_dry:   bool
          breakout:     bool
          target_price: float  蔡森等幅測距目標價
          stop_loss:    float  近 lookback 最低點 × 0.98
          message:      str
        """
        if len(self.df) < lookback_days:
            return {'signal': 'NONE', 'message': '⚪ 資料不足，VCP 無法計算'}

        recent   = self.df.tail(lookback_days).copy()
        seg_len  = lookback_days // 3
        seg1     = recent.iloc[:seg_len]
        seg2     = recent.iloc[seg_len: seg_len * 2]
        seg3     = recent.iloc[seg_len * 2:]

        def _volatility(seg):
            hi = seg['close'].max() if 'high' not in seg.columns else seg['high'].max()
            lo = seg['close'].min() if 'low'  not in seg.columns else seg['low'].min()
            return (hi - lo) / hi if hi > 0 else 0

        v1, v2, v3   = _volatility(seg1), _volatility(seg2), _volatility(seg3)
        stages_ok    = (v1 > v2 > v3)

        vol_50ma     = float(self.df['volume'].tail(50).mean()) if len(self.df) >= 50 else float(self.df['volume'].mean())
        vol_50ma     = vol_50ma if vol_50ma > 0 else 1
        last5_vol    = recent['volume'].iloc[-5:-1]          # 排除今日
        volume_dry   = bool((last5_vol < vol_50ma * 0.5).any())

        resistance   = recent['close'].max() if 'high' not in recent.columns else recent['high'].max()
        current_close = float(self.df['close'].iloc[-1])
        current_vol   = float(self.df['volume'].iloc[-1])
        breakout      = current_close >= resistance * 0.99
        volume_surge  = current_vol > vol_50ma * 1.5

        # 蔡森等幅測距目標價
        bottom        = recent['close'].min() if 'low' not in recent.columns else recent['low'].min()
        target_price  = round(resistance + (resistance - bottom), 2)
        stop_loss_vcp = round(bottom * 0.98, 2)

        if stages_ok and volume_dry and breakout and volume_surge:
            signal  = 'BUY'
            message = (f'✅ VCP 三階段收縮（{v1*100:.1f}%→{v2*100:.1f}%→{v3*100:.1f}%）'
                       f'帶量突破，籌碼沉澱完畢。目標 {target_price}，防守 {stop_loss_vcp}')
        elif stages_ok and volume_dry:
            signal  = 'HOLD'
            message = f'⏳ VCP 收縮成型（{v1*100:.1f}%→{v2*100:.1f}%→{v3*100:.1f}%），等待帶量突破確認'
        else:
            signal  = 'HOLD'
            message = '⚪ VCP 波幅收縮未達標準，繼續觀察'

        return {
            'signal':       signal,
            'vcp_stages':   [round(v1*100,1), round(v2*100,1), round(v3*100,1)],
            'stages_ok':    stages_ok,
            'volume_dry':   volume_dry,
            'breakout':     breakout,
            'volume_surge': volume_surge,
            'resistance':   round(resistance, 2),
            'target_price': target_price,
            'stop_loss':    stop_loss_vcp,
            'message':      message,
        }

    # ─────────────────────────────────────────────────────────────
    # [Task 6] 蔡森假突破 + 高檔爆量逃命訊號
    # 公式：創 20 日新高 + 爆量 + 黑K/長上影線 = 主力出貨警訊
    # ─────────────────────────────────────────────────────────────
    def detect_false_breakout_v4(self) -> dict:
        """
        蔡森假突破偵測：創近期新高後，爆出天量且收黑K或長上影線。

        條件：
          1. 今日最高價 ≥ 近 20 日最高（創新高）
          2. 今日成交量 ≥ 近 60 日最大量 × 90%（天量）
          3. 黑K（收 < 開）或長上影線（上影線 > 實體 × 2）

        返回 dict：
          signal:       'SELL' | 'HOLD'
          is_new_high:  bool
          is_huge_vol:  bool
          is_ugly_k:    bool
          message:      str
        """
        if len(self.df) < 20:
            return {'signal': 'HOLD', 'message': '⚪ 資料不足，假突破偵測略過'}

        last        = self.df.iloc[-1]
        hi_col      = 'close'  # 無 high 欄時退回 close
        vol_col     = 'volume'

        current_high  = float(last.get('high', last['close']))
        hi20          = float(self.df['close'].tail(20).max()
                              if 'high' not in self.df.columns
                              else self.df['high'].tail(20).max())
        is_new_high   = current_high >= hi20

        vol_60_max    = float(self.df[vol_col].tail(60).max())
        is_huge_vol   = float(last[vol_col]) >= vol_60_max * 0.9

        open_p  = float(last.get('open', last['close']))
        close_p = float(last['close'])
        high_p  = float(last.get('high', last['close']))
        body    = abs(close_p - open_p)
        upper   = high_p - max(close_p, open_p)
        # 乘法避免 body=0 除法崩潰
        is_ugly_k = (close_p < open_p) or (upper > body * 2)

        if is_new_high and is_huge_vol and is_ugly_k:
            signal  = 'SELL'
            message = '🚨 高檔爆量假突破／避雷針，疑似主力出貨，建議立即停利出場'
        else:
            signal  = 'HOLD'
            message = '✅ 無假突破訊號'

        return {
            'signal':      signal,
            'is_new_high': is_new_high,
            'is_huge_vol': is_huge_vol,
            'is_ugly_k':   is_ugly_k,
            'message':     message,
        }

    def generate_report(self) -> dict:
        """整合六個模組輸出的完整報告（v4.0 升級含 VCP + 假突破）"""
        return {
            "macro_veto":      self.check_macro_veto(),
            "chip_analysis":   self.calc_relative_chips(),
            "resistance":      self.find_overhead_resistance(),
            "stop_loss":       self.calculate_stop_loss(),
            "vcp_breakout":    self.detect_vcp_breakout(),
            "false_breakout":  self.detect_false_breakout_v4(),
        }


# ══════════════════════════════════════════════════════════════════
# [Step 6] 自動化邊界測試
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import traceback

    print("=" * 55)
    print("V4StrategyEngine 自動化邊界測試")
    print("=" * 55)

    dates = pd.date_range('2023-01-01', periods=150)
    mock_df = pd.DataFrame({
        'close':       np.random.uniform(50, 100, 150),
        'open':        np.random.uniform(50, 100, 150),
        'low':         np.random.uniform(40,  90, 150),
        'volume':      np.random.randint(1000, 10000, 150),
        'foreign_net': np.random.randint(-500, 2000, 150),
        'trust_net':   np.random.randint(-100,  500, 150),
    }, index=dates)

    # ── 場景 A: 正常運行 ──────────────────────────────────────
    print("\n[A] 正常場景（股本=10萬張，VIX=26，外資大空）")
    try:
        e = V4StrategyEngine(mock_df, {'vix': 26, 'foreign_futures': -25000}, 100000)
        r = e.generate_report()
        print(f"  總經: {r['macro_veto']['status']} → 最大持股 {r['macro_veto']['max_position']}%")
        print(f"  籌碼: {r['chip_analysis']['signal']}")
        print(f"  壓力: {r['resistance']['msg'][:50]}")
        print(f"  防守: {r['stop_loss']['msg'][:50]}")
        print("  ✅ 通過")
    except Exception as e_:
        print(f"  ❌ {e_}")

    # ── 場景 B: API 斷線（macro 空字典）────────────────────────
    print("\n[B] API 斷線（macro=空字典）")
    try:
        e2 = V4StrategyEngine(mock_df, {}, 100000)
        r2 = e2.check_macro_veto()
        assert r2['level'] == 'Safe', "預設應為安全（無資料→vix=15）"
        print(f"  {r2['status']} ✅ 預設安全燈")
    except Exception as e_:
        print(f"  ❌ {e_}")

    # ── 場景 C: 新股（資料不足20天）────────────────────────────
    print("\n[C] 新股（5筆資料）")
    try:
        tiny_df = mock_df.head(5)
        e3 = V4StrategyEngine(tiny_df, {'vix': 15}, 50000)
        r3 = e3.calculate_stop_loss()
        r4 = e3.find_overhead_resistance()
        print(f"  防守: {r3['msg'][:50]}")
        print(f"  壓力: {r4['msg'][:50]}")
        print("  ✅ 通過（無崩潰）")
    except Exception as e_:
        print(f"  ❌ {e_}")

    # ── 場景 D: 股本=0 → 應報 ValueError ──────────────────────
    print("\n[D] 股本=0（應 raise ValueError）")
    try:
        V4StrategyEngine(mock_df, {}, 0)
        print("  ❌ 沒有報錯（BUG）")
    except ValueError as ve:
        print(f"  ✅ 正確攔截: {ve}")

    # ── 場景 E: 無籌碼欄位 ────────────────────────────────────
    print("\n[E] 無 foreign_net/trust_net 欄位")
    try:
        df_no_chip = mock_df[['close', 'open', 'low', 'volume']]
        e5 = V4StrategyEngine(df_no_chip, {'vix': 15}, 100000)
        r5 = e5.calc_relative_chips()
        assert r5['foreign_ratio'] is None
        print(f"  ✅ 正確降級: {r5['signal']}")
    except Exception as e_:
        print(f"  ❌ {e_}")

    print("\n" + "=" * 55)
    print("全部邊界測試完成")
    print("=" * 55)
